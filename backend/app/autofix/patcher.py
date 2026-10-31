"""Auto-Fix Engine: Computes documentation patches, unified diffs, and applies approved fixes."""
from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backend.app.analyzer.models import Finding, Verdict


@dataclass
class FixPreview:
    finding: Finding
    file_path: str
    original_text: str
    updated_text: str
    diff: str
    is_applicable: bool = True
    error_message: Optional[str] = None


def generate_fix_preview(repo_root: Path, finding: Finding) -> FixPreview:
    """Generates a side-by-side before-and-after diff for a documentation fix."""
    target_path = repo_root / finding.doc_file
    if not target_path.exists():
        return FixPreview(
            finding=finding,
            file_path=finding.doc_file,
            original_text="",
            updated_text="",
            diff="",
            is_applicable=False,
            error_message=f"File {finding.doc_file} does not exist",
        )

    original_content = target_path.read_text(encoding="utf-8", errors="ignore")
    lines = original_content.splitlines(keepends=True)

    # If we have an outdated excerpt and suggested fix
    if finding.outdated_excerpt and finding.suggested_fix:
        # Search for the excerpt in the document
        raw_excerpt = finding.outdated_excerpt.strip()
        raw_fix = finding.suggested_fix.strip()

        # Try line-specific replacement first
        replaced = False
        new_lines: list[str] = []
        for line in lines:
            if not replaced and raw_excerpt in line:
                new_lines.append(line.replace(raw_excerpt, raw_fix))
                replaced = True
            else:
                new_lines.append(line)

        if not replaced and raw_excerpt in original_content:
            updated_content = original_content.replace(raw_excerpt, raw_fix, 1)
        else:
            updated_content = "".join(new_lines)
    else:
        return FixPreview(
            finding=finding,
            file_path=finding.doc_file,
            original_text=original_content,
            updated_text=original_content,
            diff="",
            is_applicable=False,
            error_message="No suggested fix available",
        )

    diff_lines = list(
        difflib.unified_diff(
            original_content.splitlines(keepends=True),
            updated_content.splitlines(keepends=True),
            fromfile=f"a/{finding.doc_file}",
            tofile=f"b/{finding.doc_file}",
        )
    )

    return FixPreview(
        finding=finding,
        file_path=finding.doc_file,
        original_text=original_content,
        updated_text=updated_content,
        diff="".join(diff_lines),
        is_applicable=True,
    )


def apply_fix(repo_root: Path, preview: FixPreview) -> bool:
    """Applies the fix safely to the documentation file."""
    if not preview.is_applicable or not preview.updated_text:
        return False
    target = repo_root / preview.file_path
    target.write_text(preview.updated_text, encoding="utf-8")
    return True

