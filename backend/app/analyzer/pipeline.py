"""DocGuard Analysis Pipeline Coordinator."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from backend.app.ai.intelligence import HeuristicAIProvider, get_ai_provider
from backend.app.analyzer.ast_analyzer import compare_python_ast, parse_python_ast
from backend.app.analyzer.doc_chunker import load_docs_at_ref
from backend.app.analyzer.doc_mapper import map_changes_to_docs
from backend.app.analyzer.models import ChangeType, CodeChange, DocSection, Finding, Verdict


# Local models are slow, so only the most relevant candidates reach Qwen.
MAX_MODEL_CALLS = 8

# A PR comment should stay short enough that people read it.
MAX_REPORTED = 10

# Sentences about the past are allowed to mention old values.
HISTORICAL_RE = re.compile(
    r"\b(before|prior to|previously|formerly|used to|until|deprecated|no longer|was (renamed|changed|replaced))\b",
    re.IGNORECASE,
)
TEST_FILE_RE = re.compile(r"(^|/)(tests?/|test_[^/]*$|[^/]*_test\.py$|conftest\.py$)")


def is_user_facing(change: CodeChange) -> bool:
    """Private names and tests aren't documented for users, so changes to them can't cause drift."""
    if TEST_FILE_RE.search(change.file_path):
        return False
    return not change.symbol_name.split(".")[-1].startswith("_")


def keep_one_issue_per_sentence(findings: list[Finding]) -> list[Finding]:
    """A maintainer fixes sentences, so each wrong sentence should count as one issue."""
    drifts = [f for f in findings if f.verdict != Verdict.NO_DRIFT_DETECTED]

    # Once a change has a confirmed sentence, a sentence that only shares its value is probably a coincidence.
    confirmed_symbols = {
        (f.source_file, f.changed_symbol) for f in drifts if f.verdict == Verdict.CONFIRMED_DRIFT
    }
    drifts = [
        f
        for f in drifts
        if f.verdict == Verdict.CONFIRMED_DRIFT or (f.source_file, f.changed_symbol) not in confirmed_symbols
    ]

    # Several code changes can make one sentence wrong. Keep the most certain, and name the others.
    kept: dict[tuple[str, int], Finding] = {}
    causes: dict[tuple[str, int], list[str]] = {}
    for finding in sorted(drifts, key=lambda f: (f.verdict != Verdict.CONFIRMED_DRIFT, -f.confidence)):
        key = (finding.doc_file, finding.doc_start_line)
        if key not in kept:
            kept[key] = finding
            causes[key] = [finding.changed_symbol]
        elif finding.changed_symbol not in causes[key]:
            causes[key].append(finding.changed_symbol)

    for key, finding in kept.items():
        others = causes[key][1:]
        if others:
            names = ", ".join(f"'{name}'" for name in others)
            finding.explanation = f"{finding.explanation} Also affected by {names}."
            finding.evidence.append(f"Also affected by: {', '.join(others)}")

    return [f for f in findings if f.verdict == Verdict.NO_DRIFT_DETECTED] + list(kept.values())


def run_git_cmd(*args: str, cwd: Optional[Path] = None) -> str:
    res = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or f"git {' '.join(args)} failed with code {res.returncode}")
    return res.stdout


@dataclass
class ScanResult:
    base_ref: str
    head_ref: str
    code_changes: list[CodeChange] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    total_drifts: int = 0
    confirmed_drifts: int = 0
    possible_drifts: int = 0
    health_score: float = 100.0

    def drifts(self) -> list[Finding]:
        """Drift findings, the most certain first."""
        found = [f for f in self.findings if f.verdict != Verdict.NO_DRIFT_DETECTED]
        return sorted(found, key=lambda f: (f.verdict != Verdict.CONFIRMED_DRIFT, -f.confidence))

    def generate_markdown_report(self, link_base: Optional[str] = None) -> str:
        """Writes the PR comment. With link_base, file names link to the exact lines on GitHub."""

        def location(path: str, line: int) -> str:
            text = f"`{path}:{line}`"
            return f"[{text}]({link_base}/{quote(path)}#L{line})" if link_base else text

        drifts = self.drifts()
        lines = ["## DocGuard report", ""]

        if not drifts:
            checked = len(self.code_changes)
            lines.append(f"No drift found. Checked {checked} code change{'' if checked == 1 else 's'}.")
            return "\n".join(lines) + "\n"

        count = len(drifts)
        lines += [f"This change probably made **{count} sentence{'' if count == 1 else 's'}** in the docs wrong.", ""]

        for f in drifts[:MAX_REPORTED]:
            label = "" if f.verdict == Verdict.CONFIRMED_DRIFT else " (possible)"
            lines += [
                f"### {location(f.doc_file, f.doc_start_line)}{label}",
                "",
                f"> {f.outdated_excerpt}",
                "",
                f"**Caused by** {location(f.source_file, f.source_line)}: {f.explanation}",
                "",
            ]
            if f.suggested_fix:
                lines += ["**Suggested fix:**", "", f"> {f.suggested_fix}", ""]

        if count > MAX_REPORTED:
            lines += [f"...and {count - MAX_REPORTED} more.", ""]

        engines = sorted({f.engine for f in drifts})
        lines.append(f"<sub>Checked by: {', '.join(engines)}. This check never blocks a merge unless you turn that on.</sub>")
        return "\n".join(lines) + "\n"


def audit_repository_drift(repo_root: Path, doc_sections: list[DocSection]) -> list[Finding]:
    """Audits the full repository state to detect any active drift between Python source code and docs."""
    py_files = [
        p
        for p in repo_root.glob("**/*.py")
        if not any(part in {".git", ".venv", "node_modules", "__pycache__", "tests"} for part in p.parts)
    ]

    findings: list[Finding] = []

    for py in py_files:
        try:
            rel_py = str(py.relative_to(repo_root))
            ast_data = parse_python_ast(py.read_text(encoding="utf-8", errors="ignore"))
            if not ast_data:
                continue

            for name, (val_str, line_no) in ast_data.constants.items():
                for sec in doc_sections:
                    # Ignore README self-referential example reports
                    if "README" in sec.file_path and "Issue #" in sec.content:
                        continue

                    if name in sec.symbols_mentioned or re.search(rf"\b{re.escape(name)}\b", sec.content):
                        for offset, line_text in enumerate(sec.content.splitlines()):
                            if name in line_text:
                                # Check numbers in line
                                nums = re.findall(r"\b\d+\b", line_text)
                                if val_str.isdigit() and nums and (val_str not in nums):
                                    conflicting_num = nums[0]
                                    doc_line = sec.start_line + offset
                                    fix = re.sub(
                                        rf"\b{re.escape(conflicting_num)}\b",
                                        val_str,
                                        line_text.strip(),
                                        count=1,
                                    )
                                    findings.append(
                                        Finding(
                                            verdict=Verdict.CONFIRMED_DRIFT,
                                            confidence=0.98,
                                            source_file=rel_py,
                                            changed_symbol=name,
                                            doc_file=sec.file_path,
                                            doc_start_line=doc_line,
                                            doc_end_line=doc_line,
                                            outdated_excerpt=line_text.strip(),
                                            explanation=f"Code defines '{name} = {val_str}' in {rel_py}:{line_no}, but documentation states '{conflicting_num}'.",
                                            suggested_fix=fix,
                                            change_type=ChangeType.CONSTANT_CHANGED,
                                            code_diff=f"{name} = {val_str}",
                                            evidence=[
                                                f"Source: {rel_py}:{line_no} sets {name} = {val_str}",
                                                f"Documentation: {sec.file_path}:{doc_line} states '{conflicting_num}'",
                                            ],
                                        )
                                    )
                                    break
        except Exception:
            continue

    return findings


def run_analysis(
    repo_root: Path,
    base_ref: str,
    head_ref: str,
    audit: bool = False,
    confidence_threshold: float = 0.0,
) -> ScanResult:
    """Executes full DocGuard pipeline on git repository between base_ref and head_ref."""
    # 1. Get changed files
    try:
        names = run_git_cmd("diff", "--name-only", f"{base_ref}...{head_ref}", cwd=repo_root).splitlines()
    except RuntimeError:
        # Unrelated histories have no three-dot diff. If this fails too, we must not report "no drift".
        try:
            names = run_git_cmd("diff", "--name-only", base_ref, head_ref, cwd=repo_root).splitlines()
        except RuntimeError as exc:
            raise RuntimeError(
                f"Could not compare {base_ref} with {head_ref}. "
                "In GitHub Actions, set fetch-depth: 0 on actions/checkout."
            ) from exc

    all_changes: list[CodeChange] = []

    for fn in names:
        if not fn.endswith(".py"):
            continue
        try:
            old_src = run_git_cmd("show", f"{base_ref}:{fn}", cwd=repo_root)
        except Exception:
            old_src = ""
        try:
            new_src = run_git_cmd("show", f"{head_ref}:{fn}", cwd=repo_root)
        except Exception:
            new_src = ""

        file_changes = compare_python_ast(fn, old_src, new_src)
        all_changes.extend(file_changes)

    all_changes = [c for c in all_changes if is_user_facing(c)]

    # 2. Load documentation as it is at the head commit, including the PR's own doc edits
    doc_sections = load_docs_at_ref(repo_root, head_ref)

    # 3. Map changes to doc candidates, most relevant first
    candidates = sorted(
        map_changes_to_docs(all_changes, doc_sections),
        key=lambda pair: pair.relevance_score,
        reverse=True,
    )

    # 4. Decide each candidate
    ai_provider = get_ai_provider()
    heuristic = HeuristicAIProvider()
    findings: list[Finding] = []
    for index, cand in enumerate(candidates):
        provider = ai_provider if index < MAX_MODEL_CALLS else heuristic
        finding = provider.evaluate(cand)
        finding.source_line = cand.change.line_number

        if HISTORICAL_RE.search(finding.outdated_excerpt):
            continue
        if finding.verdict == Verdict.CONFIRMED_DRIFT and finding.confidence < confidence_threshold:
            finding.verdict = Verdict.POSSIBLE_DRIFT

        findings.append(finding)

    # 5. A PR is only told about what it broke. The whole-repository check is a separate, explicit request.
    if audit:
        existing_symbols = {f.changed_symbol for f in findings}
        for af in audit_repository_drift(repo_root, doc_sections):
            if af.changed_symbol not in existing_symbols:
                findings.append(af)

    findings = keep_one_issue_per_sentence(findings)

    # Calculate statistics
    confirmed = sum(1 for f in findings if f.verdict == Verdict.CONFIRMED_DRIFT)
    possible = sum(1 for f in findings if f.verdict == Verdict.POSSIBLE_DRIFT)
    total_drifts = confirmed + possible

    # Health score formula: 100 - (confirmed * 18 + possible * 6)
    health = max(0.0, min(100.0, 100.0 - (confirmed * 18.0 + possible * 6.0)))

    return ScanResult(
        base_ref=base_ref,
        head_ref=head_ref,
        code_changes=all_changes,
        findings=findings,
        total_drifts=total_drifts,
        confirmed_drifts=confirmed,
        possible_drifts=possible,
        health_score=health,
    )
