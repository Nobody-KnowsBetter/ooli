#!/usr/bin/env python3
"""DocGuard: AI-Powered Documentation Intelligence Platform.

Maintains backward-compatibility with GitHub Actions while leveraging
AST analysis, hybrid candidate mapping, and evidence-grounded AI reasoning.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to sys.path so backend imports succeed
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def run_legacy_fallback(base: str, head: str, report_path: str) -> int:
    """Original MVP heuristic fallback to guarantee zero regression."""
    import re
    import subprocess

    assignment = re.compile(
        r"^(?P<name>[A-Z][A-Z0-9_]*)\s*=\s*(?P<value>[^#\n]+?)\s*(?:#.*)?$",
        re.MULTILINE,
    )

    def git(*args: str) -> str:
        res = subprocess.run(["git", *args], text=True, capture_output=True, check=False)
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip() or f"git {' '.join(args)} failed")
        return res.stdout

    def parse_assignments(text: str) -> dict[str, str]:
        return {m.group("name"): m.group("value").strip().strip("'\"") for m in assignment.finditer(text)}

    names = git("diff", "--name-only", f"{base}...{head}").splitlines()
    changes = []
    for fn in names:
        if not fn.endswith(".py"):
            continue
        try:
            old_text = git("show", f"{base}:{fn}")
        except Exception:
            old_text = ""
        try:
            new_text = git("show", f"{head}:{fn}")
        except Exception:
            continue
        old_vals = parse_assignments(old_text)
        new_vals = parse_assignments(new_text)
        for name in sorted(old_vals.keys() & new_vals.keys()):
            if old_vals[name] != new_vals[name]:
                changes.append((fn, name, old_vals[name], new_vals[name]))

    docs = [p for p in Path(".").glob("**/*.md") if ".git" not in p.parts and p.name != Path(report_path).name]
    issues = []
    for source, name, old, new in changes:
        for doc in docs:
            text = doc.read_text(encoding="utf-8", errors="ignore")
            if old in text and new not in text:
                issues.append((source, name, old, new, str(doc)))

    lines = ["## DocGuard report", ""]
    if issues:
        lines += [f"⚠️ **Potential documentation drift found: {len(issues)}**", ""]
        for source, name, old, new, doc in issues:
            lines += [
                f"- **{doc}** may be outdated.",
                f"  - Related code: `{source}`",
                f"  - Changed constant: `{name}`",
                f"  - Code changed: `{old}` → `{new}`",
                f"  - Evidence: the documentation contains `{old}` but not `{new}`.",
                "",
            ]
    else:
        lines += [
            "✅ No potential drift found by the MVP checks.",
            "",
            "Note: this is a heuristic scan, not proof that all documentation is correct.",
        ]
    report = "\n".join(lines) + "\n"
    Path(report_path).write_text(report, encoding="utf-8")
    print(report)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="DocGuard Documentation Intelligence Scanner")
    parser.add_argument("--base", default="HEAD~1", help="Base commit SHA or branch (default: HEAD~1)")
    parser.add_argument("--head", default="HEAD", help="Head commit SHA or branch (default: HEAD)")
    parser.add_argument("--report", default="docguard-report.md", help="Path to write markdown report")
    parser.add_argument("--autofix", action="store_true", help="Automatically apply suggested fixes")
    parser.add_argument("--audit", action="store_true", help="Run full repository documentation audit")
    args = parser.parse_args()

    try:
        from backend.app.analyzer.pipeline import run_analysis
        from backend.app.autofix.patcher import apply_fix, generate_fix_preview

        scan = run_analysis(repo_root=PROJECT_ROOT, base_ref=args.base, head_ref=args.head)
        report_content = scan.generate_markdown_report()
        Path(args.report).write_text(report_content, encoding="utf-8")
        print(report_content)

        if args.autofix and scan.findings:
            applied = 0
            for f in scan.findings:
                if f.suggested_fix:
                    preview = generate_fix_preview(PROJECT_ROOT, f)
                    if preview.is_applicable and apply_fix(PROJECT_ROOT, preview):
                        applied += 1
            print(f"Applied {applied} automated documentation fixes.")

        return 0
    except Exception as exc:
        print(f"Notice: Running resilient fallback analyzer due to: {exc}", file=sys.stderr)
        return run_legacy_fallback(args.base, args.head, args.report)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"DocGuard fatal error: {exc}", file=sys.stderr)
        raise SystemExit(2)
