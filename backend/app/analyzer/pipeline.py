"""DocGuard Analysis Pipeline Coordinator."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from backend.app.ai.intelligence import HeuristicAIProvider, get_ai_provider
from backend.app.analyzer.ast_analyzer import compare_python_ast, parse_python_ast
from backend.app.analyzer.doc_chunker import load_docs_at_ref
from backend.app.analyzer.doc_mapper import map_changes_to_docs
from backend.app.analyzer.models import ChangeType, CodeChange, DocSection, Finding, Verdict


# Local models are slow, so only the most relevant candidates reach Qwen.
MAX_MODEL_CALLS = 8

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

    def generate_markdown_report(self) -> str:
        lines = [
            "## 🛡️ DocGuard Documentation Intelligence Report",
            "",
        ]

        drift_findings = [f for f in self.findings if f.verdict in {Verdict.CONFIRMED_DRIFT, Verdict.POSSIBLE_DRIFT}]

        if not drift_findings:
            lines += [
                "✅ **No documentation drift detected.**",
                "",
                "Documentation accurately reflects recent code modifications.",
                "",
                f"- Evaluated **{len(self.code_changes)}** code modifications.",
                f"- Health Score: **{self.health_score:.0f}%**",
            ]
            return "\n".join(lines) + "\n"

        lines += [
            f"⚠️ **Documentation drift detected! ({len(drift_findings)} issue{'s' if len(drift_findings) != 1 else ''} found)**",
            "",
            f"Repository Documentation Health: **{self.health_score:.0f}%**",
            "",
            "---",
        ]

        for i, f in enumerate(drift_findings, start=1):
            badge = "🔴 CONFIRMED DRIFT" if f.verdict == Verdict.CONFIRMED_DRIFT else "🟡 POSSIBLE DRIFT"
            lines += [
                f"### Issue #{i}: `{f.changed_symbol}` in `{f.doc_file}`",
                "",
                f"**Verdict**: {badge} &nbsp;|&nbsp; **Confidence**: `{f.confidence * 100:.0f}%`",
                "",
                f"- **Source File**: `{f.source_file}`",
                f"- **Documentation File**: `{f.doc_file}` (Line {f.doc_start_line})",
                "",
                f"**Outdated Statement in Documentation:**",
                f"> {f.outdated_excerpt}",
                "",
                f"**Why this is incorrect:**",
                f"{f.explanation}",
                "",
            ]

            if f.code_diff:
                lines += [
                    "**Related Code Diff:**",
                    "```diff",
                    f"{f.code_diff}",
                    "```",
                    "",
                ]

            if f.suggested_fix:
                lines += [
                    "**Suggested Correction:**",
                    f"> {f.suggested_fix}",
                    "",
                ]

            if f.evidence:
                lines += ["**Supporting Evidence:**"]
                for ev in f.evidence:
                    lines.append(f"- {ev}")
                lines.append("")

            lines.append("---")

        lines += [
            "",
            "💡 *Run `python backend/src/docguard.py --autofix` or approve suggestions in the DocGuard Dashboard to apply fixes.*",
        ]
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
    except Exception:
        # Fallback for two-dot diff or single commit
        try:
            names = run_git_cmd("diff", "--name-only", base_ref, head_ref, cwd=repo_root).splitlines()
        except Exception:
            names = []

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
    seen: set[tuple[str, int, str]] = set()
    for index, cand in enumerate(candidates):
        provider = ai_provider if index < MAX_MODEL_CALLS else heuristic
        finding = provider.evaluate(cand)

        if HISTORICAL_RE.search(finding.outdated_excerpt):
            continue
        if finding.verdict == Verdict.CONFIRMED_DRIFT and finding.confidence < confidence_threshold:
            finding.verdict = Verdict.POSSIBLE_DRIFT

        key = (finding.doc_file, finding.doc_start_line, finding.changed_symbol)
        if finding.verdict != Verdict.NO_DRIFT_DETECTED and key in seen:
            continue
        seen.add(key)
        findings.append(finding)

    # 5. A PR is only told about what it broke. The whole-repository check is a separate, explicit request.
    if audit:
        existing_symbols = {f.changed_symbol for f in findings}
        for af in audit_repository_drift(repo_root, doc_sections):
            if af.changed_symbol not in existing_symbols:
                findings.append(af)

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
