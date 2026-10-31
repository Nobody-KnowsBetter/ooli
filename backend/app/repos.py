"""Finds the code to scan: this checkout, or a public GitHub repository we clone."""
from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CLONES_DIR = PROJECT_ROOT / "backend" / ".repos"

REPO_RE = re.compile(r"^(?:https://github\.com/)?([A-Za-z0-9_-][\w.-]*)/([A-Za-z0-9_-][\w.-]*?)(?:\.git)?/?$")
# Blocks refs such as "--output=file", which git would read as an option.
SAFE_REF_RE = re.compile(r"^[A-Za-z0-9_][\w./~^-]*$")


class RepoError(Exception):
    """A problem the user can fix, shown to them as is."""


def github_clone_url() -> str:
    return (os.getenv("GITHUB_CLONE_URL") or os.getenv("GITHUB_URL") or "https://github.com").rstrip("/")


def _git(*args: str, cwd: Optional[Path] = None, timeout: int = 180, token: Optional[str] = None) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if token:
        # Passed through the environment so it's never saved in .git/config or shown in a process list.
        credentials = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env.update(
            GIT_CONFIG_COUNT="1",
            GIT_CONFIG_KEY_0=f"http.{github_clone_url()}/.extraheader",
            GIT_CONFIG_VALUE_0=f"AUTHORIZATION: basic {credentials}",
        )
    try:
        res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise RepoError(f"git {args[0]} took too long")
    if res.returncode != 0:
        raise RepoError(res.stderr.strip() or f"git {args[0]} failed")
    return res.stdout.strip()


def local_repo_id() -> str:
    """Names this checkout after its GitHub remote, such as owner/name."""
    try:
        url = _git("remote", "get-url", "origin", cwd=PROJECT_ROOT, timeout=10)
        match = re.search(r"github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?$", url)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
    except RepoError:
        pass
    return f"local/{PROJECT_ROOT.name}"


def repo_dir(repo_id: str) -> Path:
    if repo_id == local_repo_id():
        return PROJECT_ROOT
    return CLONES_DIR / repo_id.replace("/", "__")


def parse_repo_name(text: str) -> str:
    match = REPO_RE.match(text.strip())
    if not match:
        raise RepoError("Enter a GitHub repository as owner/name or https://github.com/owner/name")
    return f"{match.group(1)}/{match.group(2)}"


def clone_repo(repo_id: str, token: Optional[str] = None) -> str:
    """Clones the repository if needed and returns its default branch.

    Scanning only parses its code with `ast`. Nothing from the repository is ever run.
    """
    target = repo_dir(repo_id)
    if target != PROJECT_ROOT and not target.exists():
        CLONES_DIR.mkdir(parents=True, exist_ok=True)
        try:
            _git("clone", "--quiet", f"{github_clone_url()}/{repo_id}.git", str(target), timeout=300, token=token)
        except RepoError:
            shutil.rmtree(target, ignore_errors=True)
            raise RepoError(f"Could not clone {repo_id}. Check that it exists and you can access it.")
    return _git("rev-parse", "--abbrev-ref", "HEAD", cwd=target, timeout=10)


def merge_base_of_pr(root: Path, main_ref: str, head: str, pr_number: int) -> str:
    """Finds the commit a PR branched from, including when it has already been merged."""
    base = _git("merge-base", main_ref, head, cwd=root, timeout=10)
    if base != head:
        return base

    # Already merged, so its head is part of main. The merge commit's first parent is main before the merge.
    merges = _git(
        "rev-list", "--merges", "--ancestry-path", "--reverse", f"{head}..{main_ref}", cwd=root, timeout=30
    ).splitlines()
    if not merges:
        raise RepoError(f"PR #{pr_number} was merged without a merge commit, so its changes can't be separated")
    return _git("merge-base", f"{merges[0]}^1", head, cwd=root, timeout=10)


def resolve_refs(
    root: Path,
    repo_id: str,
    base_ref: str,
    head_ref: str,
    pr_number: Optional[int],
    token: Optional[str] = None,
) -> tuple[str, str]:
    """Works out which two commits to compare, fetching the latest from GitHub when needed."""
    if not root.exists():
        raise RepoError(f"{repo_id} isn't cloned yet. Add it on the Repositories page.")

    if pr_number is not None:
        if pr_number < 1:
            raise RepoError("Enter a valid pull request number")
        ref = f"refs/docguard/pr/{pr_number}"
        try:
            _git("fetch", "--quiet", "--force", "origin", f"pull/{pr_number}/head:{ref}", cwd=root, token=token)
        except RepoError:
            raise RepoError(f"Could not find pull request #{pr_number} on {repo_id}")
        branch = _git("rev-parse", "--abbrev-ref", "origin/HEAD", cwd=root, timeout=10)
        _git("fetch", "--quiet", "origin", branch.split("/", 1)[1], cwd=root, token=token)
        # Compare with where the PR branched off, so changes merged to main since don't count.
        head = _git("rev-parse", ref, cwd=root, timeout=10)
        return merge_base_of_pr(root, "FETCH_HEAD", head, pr_number), head

    for ref in (base_ref, head_ref):
        if not SAFE_REF_RE.match(ref):
            raise RepoError(f"Not a valid git ref: {ref}")

    if root != PROJECT_ROOT:
        # "The last commit" should mean the latest on GitHub, not the one from when it was cloned.
        try:
            _git("pull", "--quiet", "--ff-only", cwd=root, token=token)
        except RepoError as exc:
            print(f"Scanning the local copy of {repo_id}, because it couldn't be updated: {exc}", file=sys.stderr)
    return base_ref, head_ref
