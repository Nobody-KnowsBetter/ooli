"""Markdown section parser, chunker, and symbol indexer."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

from backend.app.analyzer.models import DocSection

BACKTICK_RE = re.compile(r"`([^`]+)`")
HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$")
CODE_BLOCK_RE = re.compile(r"```(?:\w+)?\n(.*?)```", re.DOTALL)
WORD_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")


def extract_symbols_from_text(text: str) -> set[str]:
    """Extracts identifiers from inline code backticks, uppercase tokens, and words."""
    symbols = set()
    # 1. Anything in backticks
    for match in BACKTICK_RE.finditer(text):
        content = match.group(1).strip()
        # could be an expression, function call, or identifier
        for word in WORD_RE.findall(content):
            symbols.add(word)
        symbols.add(content)

    # 2. Uppercase tokens (constants)
    for word in WORD_RE.findall(text):
        if word.isupper() and len(word) > 2:
            symbols.add(word)
        elif "_" in word:
            symbols.add(word)

    return symbols


def chunk_markdown_file(file_path: str, content: str) -> list[DocSection]:
    """Splits a markdown document into structured sections based on headers."""
    lines = content.splitlines()
    sections: list[DocSection] = []

    current_title = Path(file_path).stem
    current_lines: list[str] = []
    start_line = 1

    for idx, line in enumerate(lines, start=1):
        match = HEADER_RE.match(line)
        if match:
            # If we already have accumulated lines, close previous section
            if current_lines:
                sec_content = "\n".join(current_lines)
                code_blocks = CODE_BLOCK_RE.findall(sec_content)
                symbols = extract_symbols_from_text(sec_content)
                sections.append(
                    DocSection(
                        file_path=file_path,
                        title=current_title,
                        content=sec_content,
                        start_line=start_line,
                        end_line=idx - 1,
                        code_blocks=code_blocks,
                        symbols_mentioned=symbols,
                    )
                )
                current_lines = []
            current_title = match.group(2).strip()
            start_line = idx

        current_lines.append(line)

    if current_lines:
        sec_content = "\n".join(current_lines)
        code_blocks = CODE_BLOCK_RE.findall(sec_content)
        symbols = extract_symbols_from_text(sec_content)
        sections.append(
            DocSection(
                file_path=file_path,
                title=current_title,
                content=sec_content,
                start_line=start_line,
                end_line=len(lines),
                code_blocks=code_blocks,
                symbols_mentioned=symbols,
            )
        )

    return sections


IGNORE_DOC_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".next",
    ".gemini",
    ".antigravity",
    "dist",
    "build",
    ".system_generated",
}


# These files describe the past, so old values in them are correct.
HISTORY_DOC_RE = re.compile(r"(changelog|changes|history|news|release[-_ ]?notes|migrat|upgrad)", re.IGNORECASE)


def is_checked_doc(rel_path: str) -> bool:
    path = Path(rel_path)
    if path.suffix.lower() not in {".md", ".rst"} or path.name == "docguard-report.md":
        return False
    if any(part in IGNORE_DOC_PARTS for part in path.parts):
        return False
    return not HISTORY_DOC_RE.search(rel_path)


def load_docs_at_ref(repo_root: Path, ref: str) -> list[DocSection]:
    """Loads docs as they were at a commit, so a PR's own doc edits and old history scan correctly."""

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=repo_root, capture_output=True, text=True, errors="ignore", check=True
        ).stdout

    sections: list[DocSection] = []
    for rel_path in git("ls-tree", "-r", "--name-only", ref).splitlines():
        if is_checked_doc(rel_path):
            sections.extend(chunk_markdown_file(rel_path, git("show", f"{ref}:{rel_path}")))
    return sections


def load_and_chunk_docs(repo_root: Path, doc_files: Optional[list[str]] = None) -> list[DocSection]:
    """Loads all documentation files from repo root and breaks them into sections."""
    all_sections: list[DocSection] = []
    if doc_files:
        paths = [repo_root / f for f in doc_files]
    else:
        paths = list(repo_root.glob("**/*.md")) + list(repo_root.glob("**/*.rst"))

    for p in paths:
        try:
            rel_path = str(p.relative_to(repo_root))
            # Ignore git, cache, virtualenvs, reports and history files
            if not is_checked_doc(rel_path):
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            all_sections.extend(chunk_markdown_file(rel_path, text))
        except Exception:
            continue

    return all_sections

