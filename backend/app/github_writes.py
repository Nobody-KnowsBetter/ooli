"""The two things DocGuard changes on GitHub, both only as pull requests a person reviews and merges."""
from __future__ import annotations

import base64
import uuid
from typing import Any, Optional
from urllib.parse import quote

import httpx

from backend.app.github_auth import github_api

WORKFLOW_PATH = ".github/workflows/docguard.yml"
WORKFLOW_FILE = """name: DocGuard

# Runs on pull requests from forks too, so outside contributors see the report.
# DocGuard only reads the pull request's code. It never runs it.
on:
  pull_request_target:

permissions:
  contents: read
  pull-requests: write

jobs:
  docguard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: Nobody-KnowsBetter/ooli@main
"""


class GithubWriteError(Exception):
    """A problem the user can act on, shown to them as is."""


def _request(method: str, path: str, token: str, **kwargs: Any) -> httpx.Response:
    try:
        return httpx.request(
            method,
            f"{github_api()}{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=20.0,
            **kwargs,
        )
    except httpx.HTTPError:
        raise GithubWriteError("Could not reach GitHub. Try again.")


def _ok(response: httpx.Response, no_access: str) -> dict[str, Any]:
    if response.status_code in {401, 403, 404}:
        raise GithubWriteError(no_access)
    if response.status_code >= 400:
        raise GithubWriteError(f"GitHub refused this change (HTTP {response.status_code}).")
    return response.json()


def _file_path(path: str) -> str:
    return quote(path, safe="/")


def _new_branch(repo_id: str, token: str, name: str, base: str, no_access: str) -> str:
    ref = _ok(_request("GET", f"/repos/{repo_id}/git/ref/heads/{quote(base, safe='/')}", token), no_access)
    branch = f"docguard/{name}-{uuid.uuid4().hex[:6]}"
    _ok(
        _request("POST", f"/repos/{repo_id}/git/refs", token, json={"ref": f"refs/heads/{branch}", "sha": ref["object"]["sha"]}),
        no_access,
    )
    return branch


def _default_branch(repo_id: str, token: str, no_access: str) -> str:
    return _ok(_request("GET", f"/repos/{repo_id}", token), no_access)["default_branch"]


def replace_sentence(text: str, line_number: int, sentence: str, fix: str) -> Optional[str]:
    """Replaces one sentence, on its own line if it's still there, otherwise its first appearance."""
    lines = text.splitlines(keepends=True)
    index = line_number - 1
    if 0 <= index < len(lines) and sentence in lines[index]:
        lines[index] = lines[index].replace(sentence, fix, 1)
        return "".join(lines)
    return text.replace(sentence, fix, 1) if sentence in text else None


def fix_target_branch(repo_id: str, token: str, issues: list[dict[str, Any]], default_branch: str) -> str:
    """A fix for one open PR from this repository goes to that PR's branch. Everything else goes to the main branch."""
    numbers = {issue.get("pr_number") for issue in issues}
    if len(numbers) != 1 or None in numbers:
        return default_branch
    response = _request("GET", f"/repos/{repo_id}/pulls/{numbers.pop()}", token)
    if response.status_code != 200:
        return default_branch
    pull = response.json()
    same_repo = (pull.get("head", {}).get("repo") or {}).get("full_name") == repo_id
    return pull["head"]["ref"] if pull.get("state") == "open" and same_repo else default_branch


def create_fix_pull_request(repo_id: str, token: str, issues: list[dict[str, Any]]) -> str:
    """Opens one pull request that corrects these sentences, and returns its address."""
    no_access = f"You don't have write access to {repo_id}. Use Copy fix and open a pull request from your fork."
    fixable = [issue for issue in issues if issue.get("suggested_fix") and issue.get("outdated_excerpt")]
    if not fixable:
        raise GithubWriteError("These issues have no suggested text. They need rewriting by hand.")

    default_branch = _default_branch(repo_id, token, no_access)
    base = fix_target_branch(repo_id, token, fixable, default_branch)
    branch = _new_branch(repo_id, token, "fix-docs", base, no_access)

    by_file: dict[str, list[dict[str, Any]]] = {}
    for issue in fixable:
        by_file.setdefault(issue["doc_file"], []).append(issue)

    applied: list[dict[str, Any]] = []
    for path, file_issues in by_file.items():
        url = f"/repos/{repo_id}/contents/{_file_path(path)}"
        response = _request("GET", url, token, params={"ref": branch})
        if response.status_code == 404:
            continue
        current = _ok(response, no_access)
        text = base64.b64decode(current["content"]).decode("utf-8")
        updated = text
        changed = []
        for issue in file_issues:
            result = replace_sentence(updated, issue["doc_start_line"], issue["outdated_excerpt"], issue["suggested_fix"])
            if result is not None:
                updated = result
                changed.append(issue)
        if changed:
            _ok(
                _request(
                    "PUT",
                    url,
                    token,
                    json={
                        "message": f"Update {path} to match the code",
                        "content": base64.b64encode(updated.encode("utf-8")).decode(),
                        "sha": current["sha"],
                        "branch": branch,
                    },
                ),
                no_access,
            )
            applied.extend(changed)

    if not applied:
        _request("DELETE", f"/repos/{repo_id}/git/refs/heads/{quote(branch, safe='/')}", token)
        raise GithubWriteError("Those sentences have already changed in the repository, so there's nothing to fix.")

    rows = "\n".join(
        f"- `{i['doc_file']}:{i['doc_start_line']}`: {i['outdated_excerpt']} → {i['suggested_fix']}" for i in applied
    )
    pull = _ok(
        _request(
            "POST",
            f"/repos/{repo_id}/pulls",
            token,
            json={
                "title": f"Fix {len(applied)} outdated doc sentence{'' if len(applied) == 1 else 's'}",
                "head": branch,
                "base": base,
                "body": f"DocGuard found these sentences no longer match the code. Please review before merging.\n\n{rows}\n",
            },
        ),
        no_access,
    )
    return pull["html_url"]


def add_action_pull_request(repo_id: str, token: str) -> dict[str, Any]:
    """Opens a pull request adding DocGuard's workflow, unless the repository already has it."""
    no_access = f"You don't have write access to {repo_id}, so DocGuard can't add the workflow there. Ask a maintainer."
    default_branch = _default_branch(repo_id, token, no_access)
    url = f"/repos/{repo_id}/contents/{WORKFLOW_PATH}"
    if _request("GET", url, token, params={"ref": default_branch}).status_code == 200:
        return {"already_installed": True, "url": f"https://github.com/{repo_id}/blob/{default_branch}/{WORKFLOW_PATH}"}

    branch = _new_branch(repo_id, token, "add-action", default_branch, no_access)
    _ok(
        _request(
            "PUT",
            url,
            token,
            json={
                "message": "Add DocGuard to check docs on pull requests",
                "content": base64.b64encode(WORKFLOW_FILE.encode()).decode(),
                "branch": branch,
            },
        ),
        no_access,
    )
    pull = _ok(
        _request(
            "POST",
            f"/repos/{repo_id}/pulls",
            token,
            json={
                "title": "Add DocGuard to check docs on pull requests",
                "head": branch,
                "base": default_branch,
                "body": (
                    "Merging this makes DocGuard check every pull request and comment when a code change makes "
                    "a sentence in the docs wrong.\n\nIt runs in this repository's GitHub Actions. It never blocks "
                    "a merge unless you turn on `fail-on-drift`, and it only reads pull request code, never runs it.\n"
                ),
            },
        ),
        no_access,
    )
    return {"already_installed": False, "url": pull["html_url"]}


def pull_is_merged(pr_url: str, token: str) -> bool:
    """Checks a fix pull request, given its address on GitHub."""
    parts = pr_url.rstrip("/").split("/")
    if len(parts) < 4 or parts[-2] != "pull":
        return False
    response = _request("GET", f"/repos/{parts[-4]}/{parts[-3]}/pulls/{parts[-1]}", token)
    return response.status_code == 200 and bool(response.json().get("merged_at"))
