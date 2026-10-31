"""SQLite Persistence layer for DocGuard."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.app.repos import local_repo_id

DB_FILE = Path(os.getenv("DOCGUARD_DB_PATH") or Path(__file__).resolve().parent.parent.parent / "docguard.db")


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS repositories (
            id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            default_branch TEXT DEFAULT 'main',
            health_score REAL DEFAULT 100.0,
            last_scanned_at TEXT
        );
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS scan_reports (
            id TEXT PRIMARY KEY,
            repo_id TEXT,
            base_sha TEXT,
            head_sha TEXT,
            pr_number INTEGER,
            status TEXT,
            total_drifts INTEGER,
            confirmed_drifts INTEGER,
            possible_drifts INTEGER,
            health_score REAL,
            created_at TEXT,
            FOREIGN KEY (repo_id) REFERENCES repositories(id)
        );
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS findings (
            id TEXT PRIMARY KEY,
            report_id TEXT,
            verdict TEXT,
            confidence REAL,
            source_file TEXT,
            changed_symbol TEXT,
            doc_file TEXT,
            doc_start_line INTEGER,
            doc_end_line INTEGER,
            outdated_excerpt TEXT,
            explanation TEXT,
            suggested_fix TEXT,
            code_diff TEXT,
            evidence TEXT,
            is_fixed INTEGER DEFAULT 0,
            engine TEXT DEFAULT 'heuristic',
            FOREIGN KEY (report_id) REFERENCES scan_reports(id)
        );
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """
    )

    # Which signed-in maintainer can see which repositories.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_repositories (
            login TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            PRIMARY KEY (login, repo_id)
        );
    """
    )

    # Columns added since the first version, for databases that already exist
    for table, column, definition in [
        ("findings", "engine", "TEXT DEFAULT 'heuristic'"),
        ("scan_reports", "pr_title", "TEXT"),
        ("repositories", "description", "TEXT DEFAULT ''"),
        ("repositories", "language", "TEXT DEFAULT ''"),
        ("repositories", "is_private", "INTEGER DEFAULT 0"),
        ("repositories", "pushed_at", "TEXT DEFAULT ''"),
        ("repositories", "open_prs", "INTEGER DEFAULT 0"),
    ]:
        columns = {row["name"] for row in cursor.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    # This checkout is always available to scan.
    cursor.execute(
        "INSERT OR IGNORE INTO repositories (id, full_name, default_branch, health_score) VALUES (?, ?, ?, ?)",
        (local_repo_id(), local_repo_id(), "main", 100.0),
    )
    # Earlier versions listed a placeholder repository that was never actually scanned.
    cursor.execute("DELETE FROM repositories WHERE id = 'krishgarg-code/JavaBasicPrograms1'")
    # Closed APIs were removed from the project.
    cursor.execute("UPDATE settings SET value = 'qwen' WHERE key = 'ai_provider' AND value IN ('gemini', 'openai')")

    # Default settings
    default_settings = {
        "ai_provider": "qwen",
        "confidence_threshold": "0.75",
        "auto_comment": "true",
        "github_app_name": "DocGuard Platform",
    }
    for k, v in default_settings.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    conn.commit()
    conn.close()


def save_scan_report(
    report_id: str,
    repo_id: str,
    base_sha: str,
    head_sha: str,
    pr_number: Optional[int],
    total_drifts: int,
    confirmed_drifts: int,
    possible_drifts: int,
    health_score: float,
    findings: list[dict[str, Any]],
    pr_title: Optional[str] = None,
) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    cursor.execute(
        """
        INSERT INTO scan_reports (id, repo_id, base_sha, head_sha, pr_number, pr_title, status, total_drifts, confirmed_drifts, possible_drifts, health_score, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            report_id,
            repo_id,
            base_sha,
            head_sha,
            pr_number,
            pr_title,
            "COMPLETED",
            total_drifts,
            confirmed_drifts,
            possible_drifts,
            health_score,
            now,
        ),
    )

    cursor.execute(
        """
        UPDATE repositories
        SET health_score = ?, last_scanned_at = ?
        WHERE id = ?
    """,
        (health_score, now, repo_id),
    )

    # A new scan of a pull request replaces the last one, so a sentence fixed in the PR gets resolved.
    if pr_number is not None:
        cursor.execute(
            """
            UPDATE findings SET is_fixed = 1
            WHERE is_fixed = 0 AND report_id IN (
                SELECT id FROM scan_reports WHERE repo_id = ? AND pr_number = ? AND id != ?
            )
        """,
            (repo_id, pr_number, report_id),
        )

    # Only save actual drift findings (CONFIRMED_DRIFT or POSSIBLE_DRIFT)
    drift_findings = [
        f for f in findings
        if f.get("verdict") in {"CONFIRMED_DRIFT", "POSSIBLE_DRIFT"}
    ]

    for i, f in enumerate(drift_findings):
        # Scanning the same change twice shouldn't list the same sentence twice.
        cursor.execute(
            """
            SELECT 1 FROM findings x JOIN scan_reports r ON x.report_id = r.id
            WHERE r.repo_id = ? AND x.is_fixed = 0 AND x.doc_file = ? AND x.outdated_excerpt = ?
        """,
            (repo_id, f.get("doc_file"), f.get("outdated_excerpt")),
        )
        if cursor.fetchone():
            continue

        f_id = f"{report_id}-finding-{i}"
        cursor.execute(
            """
            INSERT INTO findings (id, report_id, verdict, confidence, source_file, changed_symbol, doc_file, doc_start_line, doc_end_line, outdated_excerpt, explanation, suggested_fix, code_diff, evidence, engine)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                f_id,
                report_id,
                f.get("verdict"),
                f.get("confidence"),
                f.get("source_file"),
                f.get("changed_symbol"),
                f.get("doc_file"),
                f.get("doc_start_line"),
                f.get("doc_end_line"),
                f.get("outdated_excerpt"),
                f.get("explanation"),
                f.get("suggested_fix"),
                f.get("code_diff"),
                json.dumps(f.get("evidence", [])),
                f.get("engine", "heuristic"),
            ),
        )

    conn.commit()
    conn.close()


def add_repository(repo_id: str, default_branch: str) -> None:
    conn = get_db_connection()
    conn.execute(
        "INSERT OR REPLACE INTO repositories (id, full_name, default_branch) VALUES (?, ?, ?)",
        (repo_id, repo_id, default_branch),
    )
    conn.commit()
    conn.close()


def repository_exists(repo_id: str) -> bool:
    conn = get_db_connection()
    row = conn.execute("SELECT 1 FROM repositories WHERE id = ?", (repo_id,)).fetchone()
    conn.close()
    return row is not None


def sync_user_repositories(login: str, repos: list[dict[str, Any]]) -> None:
    """Makes our copy of a maintainer's repository list match GitHub's."""
    conn = get_db_connection()
    for repo in repos:
        conn.execute(
            """
            INSERT INTO repositories (id, full_name, default_branch, description, language, is_private, pushed_at)
            VALUES (:full_name, :full_name, :default_branch, :description, :language, :private, :pushed_at)
            ON CONFLICT(id) DO UPDATE SET
                default_branch = excluded.default_branch,
                description = excluded.description,
                language = excluded.language,
                is_private = excluded.is_private,
                pushed_at = excluded.pushed_at
        """,
            repo,
        )
    conn.execute("DELETE FROM user_repositories WHERE login = ?", (login,))
    conn.executemany(
        "INSERT OR IGNORE INTO user_repositories (login, repo_id) VALUES (?, ?)",
        [(login, repo["full_name"]) for repo in repos],
    )
    conn.commit()
    conn.close()


def link_user_repository(login: str, repo_id: str) -> None:
    conn = get_db_connection()
    conn.execute("INSERT OR IGNORE INTO user_repositories (login, repo_id) VALUES (?, ?)", (login, repo_id))
    conn.commit()
    conn.close()


def user_repo_ids(login: str) -> set[str]:
    conn = get_db_connection()
    rows = conn.execute("SELECT repo_id FROM user_repositories WHERE login = ?", (login,)).fetchall()
    conn.close()
    return {row["repo_id"] for row in rows}


def get_user_repositories(login: str) -> list[dict[str, Any]]:
    """A maintainer's repositories: those needing attention first, then the most recently pushed."""
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT rp.*,
            (SELECT COUNT(*) FROM findings f JOIN scan_reports s ON f.report_id = s.id
             WHERE s.repo_id = rp.id AND f.is_fixed = 0) AS open_issues,
            (SELECT COUNT(DISTINCT s.pr_number) FROM scan_reports s WHERE s.repo_id = rp.id) AS prs_checked
        FROM repositories rp
        JOIN user_repositories u ON u.repo_id = rp.id
        WHERE u.login = ?
        ORDER BY open_issues DESC, rp.pushed_at DESC
    """,
        (login,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def set_open_prs(repo_id: str, count: int) -> None:
    conn = get_db_connection()
    conn.execute("UPDATE repositories SET open_prs = ? WHERE id = ?", (count, repo_id))
    conn.commit()
    conn.close()


def pr_already_scanned(repo_id: str, pr_number: int, head_sha: str) -> bool:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT 1 FROM scan_reports WHERE repo_id = ? AND pr_number = ? AND head_sha = ? LIMIT 1",
        (repo_id, pr_number, head_sha),
    ).fetchone()
    conn.close()
    return row is not None


def _repo_filter(column: str, repo_ids: Optional[set[str]]) -> tuple[str, list[str]]:
    """SQL limiting a query to one user's repositories. None means login is off, so no limit."""
    if repo_ids is None:
        return "", []
    marks = ",".join("?" for _ in repo_ids) or "NULL"
    return f" AND {column} IN ({marks})", list(repo_ids)


def get_reports(repo_ids: Optional[set[str]] = None) -> list[dict[str, Any]]:
    where, params = _repo_filter("repo_id", repo_ids)
    conn = get_db_connection()
    rows = conn.execute(
        f"SELECT * FROM scan_reports WHERE 1 = 1{where} ORDER BY created_at DESC LIMIT 20", params
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_issues(
    status: Optional[str] = None,
    verdict: Optional[str] = None,
    repo_ids: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT f.*, r.created_at, r.repo_id, r.pr_number, r.pr_title, r.head_sha, rp.default_branch
        FROM findings f
        JOIN scan_reports r ON f.report_id = r.id
        LEFT JOIN repositories rp ON rp.id = r.repo_id
        WHERE f.verdict IN ('CONFIRMED_DRIFT', 'POSSIBLE_DRIFT')
    """
    params: list[Any] = []
    repo_sql, repo_params = _repo_filter("r.repo_id", repo_ids)
    query += repo_sql
    params += repo_params

    if status == "open":
        query += " AND f.is_fixed = 0"
    elif status == "fixed":
        query += " AND f.is_fixed = 1"

    if verdict:
        query += " AND f.verdict = ?"
        params.append(verdict)

    query += " ORDER BY r.created_at DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    res = []
    for r in rows:
        d = dict(r)
        try:
            d["evidence"] = json.loads(d.get("evidence") or "[]")
        except Exception:
            d["evidence"] = []
        res.append(d)
    return res


def get_issue_by_id(issue_id: str) -> Optional[dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT f.*, r.created_at, r.repo_id, r.pr_number, r.pr_title, r.base_sha, r.head_sha, rp.default_branch
        FROM findings f
        JOIN scan_reports r ON f.report_id = r.id
        LEFT JOIN repositories rp ON rp.id = r.repo_id
        WHERE f.id = ?
    """,
        (issue_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    try:
        d["evidence"] = json.loads(d.get("evidence") or "[]")
    except Exception:
        d["evidence"] = []
    return d


def mark_issue_fixed(issue_id: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE findings SET is_fixed = 1 WHERE id = ?", (issue_id,))
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return success


def get_overview_data(repo_ids: Optional[set[str]] = None) -> dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    repo_where, repo_params = _repo_filter("id", repo_ids)
    report_where, report_params = _repo_filter("repo_id", repo_ids)
    joined_where, joined_params = _repo_filter("r.repo_id", repo_ids)

    cursor.execute(f"SELECT COUNT(*), AVG(health_score) FROM repositories WHERE 1 = 1{repo_where}", repo_params)
    repo_count, avg_health = cursor.fetchone()

    def count_findings(condition: str) -> int:
        cursor.execute(
            f"SELECT COUNT(*) FROM findings f JOIN scan_reports r ON f.report_id = r.id WHERE {condition}{joined_where}",
            joined_params,
        )
        return cursor.fetchone()[0]

    confirmed_count = count_findings("f.is_fixed = 0 AND f.verdict = 'CONFIRMED_DRIFT'")
    possible_count = count_findings("f.is_fixed = 0 AND f.verdict = 'POSSIBLE_DRIFT'")
    fixed_count = count_findings("f.is_fixed = 1")

    cursor.execute(
        f"SELECT COUNT(DISTINCT repo_id || '#' || pr_number) FROM scan_reports WHERE pr_number IS NOT NULL{report_where}",
        report_params,
    )
    prs_checked = cursor.fetchone()[0]

    cursor.execute(
        f"SELECT * FROM scan_reports WHERE 1 = 1{report_where} ORDER BY created_at DESC LIMIT 5", report_params
    )
    recent_reports = [dict(r) for r in cursor.fetchall()]

    cursor.execute(
        f"""
        SELECT f.*, r.repo_id, r.pr_number, r.created_at
        FROM findings f
        JOIN scan_reports r ON f.report_id = r.id
        WHERE f.is_fixed = 0 AND f.verdict IN ('CONFIRMED_DRIFT', 'POSSIBLE_DRIFT'){joined_where}
        ORDER BY r.created_at DESC
        LIMIT 6
    """,
        joined_params,
    )
    recent_issues = []
    for r in cursor.fetchall():
        d = dict(r)
        try:
            d["evidence"] = json.loads(d.get("evidence") or "[]")
        except Exception:
            d["evidence"] = []
        recent_issues.append(d)

    conn.close()

    return {
        "repository_count": repo_count or 0,
        "avg_health_score": round(avg_health if avg_health is not None else 100.0, 1),
        "total_active_drifts": confirmed_count + possible_count,
        "confirmed_drifts": confirmed_count,
        "possible_drifts": possible_count,
        "resolved_drifts": fixed_count,
        "prs_checked": prs_checked,
        "recent_reports": recent_reports,
        "recent_issues": recent_issues,
    }


def get_settings_data() -> dict[str, str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def update_settings_data(updates: dict[str, str]) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    for k, v in updates.items():
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
    conn.commit()
    conn.close()
