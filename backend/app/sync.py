"""Keeps each signed-in maintainer's dashboard up to date, so nobody has to add repos or press scan.

While someone is signed in, this finds their repositories, and scans every open pull request
it hasn't seen at that commit. Only repositories with open pull requests get cloned.
"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from backend.app.analyzer.pipeline import ScanResult, run_analysis
from backend.app.database.db import (
    get_settings_data,
    pr_already_scanned,
    save_scan_report,
    set_open_prs,
    sync_user_repositories,
)
from backend.app.github_auth import (
    Session,
    list_open_pulls,
    list_user_repos,
    live_sessions,
    sync_wanted,
)
from backend.app.repos import clone_repo, repo_dir, resolve_refs

SYNC_SECONDS = 120
REPO_LIST_MAX_AGE_SECONDS = 60
# Limits per sync, so one big account can't tie up the model and the disk.
MAX_REPOS_PER_SYNC = 15
MAX_PULLS_PER_REPO = 5
ACTIVE_DAYS = 90

scan_lock = threading.Lock()  # Git and the model handle one scan at a time.
statuses: dict[str, dict[str, Any]] = {}
repo_list_synced_at: dict[str, float] = {}


def scan_repository(
    repo_id: str,
    token: Optional[str],
    base_ref: str = "HEAD~1",
    head_ref: str = "HEAD",
    pr_number: Optional[int] = None,
    pr_title: Optional[str] = None,
    audit: bool = False,
) -> tuple[str, str, str, ScanResult]:
    """Scans a change and saves the report. Returns the report id, both commits and the result."""
    with scan_lock:
        root = repo_dir(repo_id)
        if not root.exists():
            clone_repo(repo_id, token)
        base, head = resolve_refs(root, repo_id, base_ref, head_ref, pr_number, token)
        scan = run_analysis(
            repo_root=root,
            base_ref=base,
            head_ref=head,
            audit=audit,
            confidence_threshold=float(get_settings_data().get("confidence_threshold", 0.0)),
        )
        report_id = f"report-{uuid.uuid4().hex[:8]}"
        save_scan_report(
            report_id=report_id,
            repo_id=repo_id,
            base_sha=base,
            head_sha=head,
            pr_number=pr_number,
            pr_title=pr_title,
            total_drifts=scan.total_drifts,
            confirmed_drifts=scan.confirmed_drifts,
            possible_drifts=scan.possible_drifts,
            health_score=scan.health_score,
            findings=[f.to_dict() for f in scan.findings],
        )
    return report_id, base, head, scan


def refresh_repo_list(session: Session, force: bool = False) -> list[dict[str, Any]]:
    """Copies the maintainer's repositories from GitHub, unless that was done moments ago."""
    age = time.time() - repo_list_synced_at.get(session.login, 0)
    if not force and age < REPO_LIST_MAX_AGE_SECONDS:
        return []
    repos = list_user_repos(session.token)
    sync_user_repositories(session.login, repos)
    repo_list_synced_at[session.login] = time.time()
    return repos


def is_active(repo: dict[str, Any]) -> bool:
    try:
        pushed = datetime.fromisoformat(repo["pushed_at"].replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return False
    return pushed > datetime.now(timezone.utc) - timedelta(days=ACTIVE_DAYS)


def sync_session(session: Session) -> dict[str, Any]:
    status: dict[str, Any] = {
        "state": "syncing",
        "repos": statuses.get(session.login, {}).get("repos", 0),
        "prs_scanned": 0,
        "errors": [],
        "last_synced_at": statuses.get(session.login, {}).get("last_synced_at"),
    }
    statuses[session.login] = status

    try:
        repos = refresh_repo_list(session, force=True)
        status["repos"] = len(repos)
        # GitHub lists the most recently pushed first, so the limit keeps the ones that matter.
        for repo in [r for r in repos if is_active(r)][:MAX_REPOS_PER_SYNC]:
            repo_id = repo["full_name"]
            try:
                pulls = list_open_pulls(repo_id, session.token)
                set_open_prs(repo_id, len(pulls))
                for pull in pulls[:MAX_PULLS_PER_REPO]:
                    if pr_already_scanned(repo_id, pull["number"], pull["head_sha"]):
                        continue
                    scan_repository(repo_id, session.token, pr_number=pull["number"], pr_title=pull["title"])
                    status["prs_scanned"] += 1
            except Exception as exc:  # One broken repository shouldn't stop the others.
                print(f"Sync skipped {repo_id}: {exc}")
                status["errors"].append(repo_id)
    except Exception as exc:
        print(f"Sync failed for {session.login}: {exc}")
        status["errors"].append("GitHub")

    status["state"] = "idle"
    status["last_synced_at"] = datetime.now(timezone.utc).isoformat()
    return status


def sync_loop() -> None:
    while True:
        sync_wanted.wait(SYNC_SECONDS)
        sync_wanted.clear()
        for session in live_sessions():
            sync_session(session)


def start_background_sync() -> None:
    # Always on, since sign-in can be set up while the backend runs. With nobody signed in, it does nothing.
    threading.Thread(target=sync_loop, daemon=True, name="docguard-sync").start()
