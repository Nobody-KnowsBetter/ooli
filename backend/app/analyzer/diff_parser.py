"""Unified Git diff parser and hunk extractor."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class DiffHunk:
    old_start: int
    old_length: int
    new_start: int
    new_length: int
    header: str
    lines: list[str] = field(default_factory=list)


@dataclass
class FileDiff:
    old_path: Optional[str]
    new_path: Optional[str]
    is_new: bool = False
    is_deleted: bool = False
    is_renamed: bool = False
    hunks: list[DiffHunk] = field(default_factory=list)
    raw_patch: str = ""

    @property
    def target_path(self) -> str:
        return self.new_path or self.old_path or ""


def run_git(*args: str, cwd: Optional[Path] = None) -> str:
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


HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")


def parse_unified_diff(diff_text: str) -> list[FileDiff]:
    file_diffs: list[FileDiff] = []
    current_file: Optional[FileDiff] = None
    current_hunk: Optional[DiffHunk] = None
    patch_lines: list[str] = []

    lines = diff_text.splitlines()
    for line in lines:
        if line.startswith("diff --git "):
            if current_file:
                current_file.raw_patch = "\n".join(patch_lines)
                file_diffs.append(current_file)
            patch_lines = [line]
            current_file = FileDiff(old_path=None, new_path=None)
            current_hunk = None
        elif line.startswith("--- a/"):
            if current_file:
                current_file.old_path = line[6:]
            patch_lines.append(line)
        elif line.startswith("--- /dev/null"):
            if current_file:
                current_file.is_new = True
            patch_lines.append(line)
        elif line.startswith("+++ b/"):
            if current_file:
                current_file.new_path = line[6:]
            patch_lines.append(line)
        elif line.startswith("+++ /dev/null"):
            if current_file:
                current_file.is_deleted = True
            patch_lines.append(line)
        elif line.startswith("similarity index"):
            if current_file:
                current_file.is_renamed = True
            patch_lines.append(line)
        elif line.startswith("@@ "):
            match = HUNK_RE.match(line)
            if match and current_file:
                old_start = int(match.group(1))
                old_len = int(match.group(2) or "1")
                new_start = int(match.group(3))
                new_len = int(match.group(4) or "1")
                header = match.group(5).strip()
                current_hunk = DiffHunk(
                    old_start=old_start,
                    old_length=old_len,
                    new_start=new_start,
                    new_length=new_len,
                    header=header,
                    lines=[line],
                )
                current_file.hunks.append(current_hunk)
            patch_lines.append(line)
        else:
            if current_hunk:
                current_hunk.lines.append(line)
            patch_lines.append(line)

    if current_file:
        current_file.raw_patch = "\n".join(patch_lines)
        file_diffs.append(current_file)

    return file_diffs

