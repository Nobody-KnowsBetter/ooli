#!/usr/bin/env python3
"""DocGuard's command line: checks a code change against the docs and writes a report.

The GitHub Action runs this. It needs only Python and httpx, not the dashboard's API.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Lets `backend.app...` import from wherever this is run, such as a user's repository in CI.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.analyzer.models import Verdict  # noqa: E402
from backend.app.analyzer.pipeline import ScanResult, run_analysis  # noqa: E402
from backend.app.autofix.patcher import apply_fix, generate_fix_preview  # noqa: E402


def escape_data(text: str) -> str:
    """Docs are untrusted, so a sentence must not be able to start its own workflow command."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def escape_property(text: str) -> str:
    return escape_data(text).replace(":", "%3A").replace(",", "%2C")


def write_github_results(scan: ScanResult) -> None:
    """Marks each sentence in the PR's checks and shares the counts with later workflow steps."""
    for finding in scan.drifts():
        level = "warning" if finding.verdict == Verdict.CONFIRMED_DRIFT else "notice"
        print(
            f"::{level} file={escape_property(finding.doc_file)},line={finding.doc_start_line},"
            f"title=DocGuard::{escape_data(finding.explanation)}"
        )

    output_file = os.getenv("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a", encoding="utf-8") as output:
            output.write(f"drift-count={scan.total_drifts}\n")
            output.write(f"confirmed-count={scan.confirmed_drifts}\n")
            output.write(f"possible-count={scan.possible_drifts}\n")


def link_base(head: str) -> str | None:
    server, repository = os.getenv("GITHUB_SERVER_URL"), os.getenv("GITHUB_REPOSITORY")
    return f"{server}/{repository}/blob/{head}" if server and repository else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Finds the doc sentences a code change made wrong.")
    parser.add_argument("--base", default="HEAD~1", help="Commit before the change (default: HEAD~1)")
    parser.add_argument("--head", default="HEAD", help="Commit after the change (default: HEAD)")
    parser.add_argument("--repo-root", default=".", help="The repository to check (default: this folder)")
    parser.add_argument("--report", default="docguard-report.md", help="Where to write the Markdown report")
    parser.add_argument("--autofix", action="store_true", help="Apply suggested fixes to the docs")
    parser.add_argument("--audit", action="store_true", help="Also check the whole repository")
    parser.add_argument("--fail-on-drift", action="store_true", help="Exit with an error on confirmed drift")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    try:
        scan = run_analysis(repo_root=repo_root, base_ref=args.base, head_ref=args.head, audit=args.audit)
    except Exception as exc:  # A broken check shouldn't stop anyone's pull request.
        message = f"DocGuard could not check this change: {exc}"
        print(f"::warning title=DocGuard::{escape_data(message)}" if os.getenv("GITHUB_ACTIONS") else message)
        return 0

    report = scan.generate_markdown_report(link_base=link_base(args.head), edit_base=os.getenv("DOCGUARD_EDIT_BASE"))
    Path(args.report).write_text(report, encoding="utf-8")
    print(report)

    if os.getenv("GITHUB_ACTIONS"):
        write_github_results(scan)

    if args.autofix:
        applied = 0
        for finding in scan.drifts():
            if finding.suggested_fix:
                preview = generate_fix_preview(repo_root, finding)
                if preview.is_applicable and apply_fix(repo_root, preview):
                    applied += 1
        print(f"Applied {applied} documentation fixes.")

    return 1 if args.fail_on_drift and scan.confirmed_drifts else 0


if __name__ == "__main__":
    raise SystemExit(main())
