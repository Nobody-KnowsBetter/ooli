"""SQLite Persistence layer for DocGuard."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DB_FILE = Path(__file__).resolve().parent.parent.parent / "docguard.db"


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

    # Insert default repo if none exists
    cursor.execute("SELECT COUNT(*) FROM repositories")
    if cursor.fetchone()[0] == 0:
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            INSERT INTO repositories (id, full_name, default_branch, health_score, last_scanned_at)
            VALUES (?, ?, ?, ?, ?)
        """,
            ("krishgarg-code/JavaBasicPrograms1", "krishgarg-code/JavaBasicPrograms1", "main", 100.0, now),
        )

    # Default settings
    default_settings = {
        "ai_provider": "heuristic",
        "confidence_threshold": "0.75",
        "auto_comment": "true",
        "github_app_name": "DocGuard Platform",
        "github_installation_status": "connected",
        "monitored_branches": "main, master, staging",
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
) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    cursor.execute(
        """
        INSERT INTO scan_reports (id, repo_id, base_sha, head_sha, pr_number, status, total_drifts, confirmed_drifts, possible_drifts, health_score, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            report_id,
            repo_id,
            base_sha,
            head_sha,
            pr_number,
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

    # If this scan found 0 drifts, mark all prior open issues for this repo as resolved
    if total_drifts == 0:
        cursor.execute(
            """
            UPDATE findings
            SET is_fixed = 1
            WHERE is_fixed = 0 AND report_id IN (
                SELECT id FROM scan_reports WHERE repo_id = ?
            )
        """,
            (repo_id,),
        )

    # Only save actual drift findings (CONFIRMED_DRIFT or POSSIBLE_DRIFT)
    drift_findings = [
        f for f in findings
        if f.get("verdict") in {"CONFIRMED_DRIFT", "POSSIBLE_DRIFT"}
    ]

    for i, f in enumerate(drift_findings):
        f_id = f"{report_id}-finding-{i}"
        cursor.execute(
            """
            INSERT INTO findings (id, report_id, verdict, confidence, source_file, changed_symbol, doc_file, doc_start_line, doc_end_line, outdated_excerpt, explanation, suggested_fix, code_diff, evidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )

    conn.commit()
    conn.close()


def get_all_issues(status: Optional[str] = None, verdict: Optional[str] = None) -> list[dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT f.*, r.created_at, r.repo_id, r.pr_number
        FROM findings f
        JOIN scan_reports r ON f.report_id = r.id
        WHERE f.verdict IN ('CONFIRMED_DRIFT', 'POSSIBLE_DRIFT')
    """
    params: list[Any] = []

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
        SELECT f.*, r.created_at, r.repo_id, r.pr_number, r.base_sha, r.head_sha
        FROM findings f
        JOIN scan_reports r ON f.report_id = r.id
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


def get_overview_data() -> dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*), AVG(health_score) FROM repositories")
    repo_count, avg_health = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) FROM findings WHERE is_fixed = 0 AND verdict = 'CONFIRMED_DRIFT'")
    confirmed_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM findings WHERE is_fixed = 0 AND verdict = 'POSSIBLE_DRIFT'")
    possible_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM findings WHERE is_fixed = 1")
    fixed_count = cursor.fetchone()[0]

    cursor.execute("SELECT * FROM scan_reports ORDER BY created_at DESC LIMIT 5")
    recent_reports = [dict(r) for r in cursor.fetchall()]

    cursor.execute(
        """
        SELECT f.*, r.repo_id, r.created_at
        FROM findings f
        JOIN scan_reports r ON f.report_id = r.id
        WHERE f.is_fixed = 0 AND f.verdict IN ('CONFIRMED_DRIFT', 'POSSIBLE_DRIFT')
        ORDER BY r.created_at DESC
        LIMIT 6
    """
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
        "repository_count": repo_count or 1,
        "avg_health_score": round(avg_health if avg_health is not None else 100.0, 1),
        "total_active_drifts": confirmed_count + possible_count,
        "confirmed_drifts": confirmed_count,
        "possible_drifts": possible_count,
        "resolved_drifts": fixed_count,
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
