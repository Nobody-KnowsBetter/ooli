"""DocGuard FastAPI Application."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

# Ensure project root is in sys.path regardless of execution directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / "backend" / ".env")  # Runs first, because the imports below read settings.

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.app.ai.intelligence import model_status, selected_provider_name
from backend.app.analyzer.models import Finding, Verdict
from backend.app.analyzer.pipeline import run_analysis
from backend.app.autofix.patcher import FixPreview, apply_fix, generate_fix_preview
from backend.app.database.db import (
    add_repository,
    get_all_issues,
    get_db_connection,
    get_reports as get_visible_reports,
    get_user_repositories,
    link_user_repository,
    user_repo_ids,
    get_issue_by_id,
    get_overview_data,
    get_settings_data,
    init_db,
    mark_issue_fixed,
    repository_exists,
    update_settings_data,
)
from backend.app.github_auth import current_session, login_enabled, router as github_router, sync_wanted, token_for
from backend.app.sync import refresh_repo_list, scan_repository, start_background_sync, statuses
from backend.app.repos import RepoError, clone_repo, local_repo_id, parse_repo_name, repo_dir, resolve_refs


# Ensure database tables exist immediately
init_db()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    init_db()
    start_background_sync()
    yield


app = FastAPI(
    title="DocGuard Documentation Intelligence API",
    description="Detects, explains, and fixes documentation drift using AST and AI reasoning.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(github_router)

# These must work before login. GitHub signs its own webhook calls.
PUBLIC_API_PREFIXES = ("/api/auth/", "/api/health", "/api/webhook/")


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if (
        login_enabled()
        and path.startswith("/api/")
        and not path.startswith(PUBLIC_API_PREFIXES)
        and not current_session(request)
    ):
        return JSONResponse({"detail": "Log in with GitHub first"}, status_code=401)
    return await call_next(request)


# Enable CORS for Next.js dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # This API can edit files.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    """This server is only the API. The dashboard runs separately on port 3000."""
    return {
        "service": "DocGuard API",
        "dashboard": "http://localhost:3000",
        "api_docs": "http://localhost:8000/docs",
    }


class ScanRequest(BaseModel):
    base_ref: str = "HEAD~1"
    head_ref: str = "HEAD"
    repo_id: Optional[str] = None  # Defaults to this checkout.
    pr_number: Optional[int] = None  # Scans that pull request instead of base_ref/head_ref.
    audit: bool = False  # Also check the whole repository, not only this change.


class AddRepositoryRequest(BaseModel):
    repository: str


class AutoFixRequest(BaseModel):
    doc_file: str
    outdated_excerpt: str
    suggested_fix: str
    issue_id: Optional[str] = None
    repo_id: Optional[str] = None


class SettingsUpdateRequest(BaseModel):
    ai_provider: Optional[str] = None
    confidence_threshold: Optional[str] = None
    auto_comment: Optional[str] = None


def visible_repos(request: Request) -> Optional[set[str]]:
    """The repositories this user may see. None means login is off, so there's no limit."""
    session = current_session(request)
    if not login_enabled() or not session:
        return None
    return user_repo_ids(session.login)


def require_repo_access(request: Request, repo_id: str) -> None:
    allowed = visible_repos(request)
    if allowed is not None and repo_id not in allowed:
        raise HTTPException(status_code=404, detail=f"Unknown repository: {repo_id}")


def _visible_issue(request: Request, issue_id: str) -> dict[str, Any]:
    issue = get_issue_by_id(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    require_repo_access(request, issue.get("repo_id", ""))
    return issue


def _no_local_fixes_when_hosted() -> None:
    # Signed-in users don't own this server's copy, so a fix there wouldn't reach their repository.
    if login_enabled():
        raise HTTPException(status_code=400, detail="Use Edit on GitHub to fix this in your repository")


def _preview_for_issue(issue: dict[str, Any]) -> FixPreview:
    finding = Finding(
        verdict=Verdict(issue.get("verdict", "CONFIRMED_DRIFT")),
        confidence=float(issue.get("confidence", 1.0)),
        source_file=issue.get("source_file", ""),
        changed_symbol=issue.get("changed_symbol", ""),
        doc_file=issue.get("doc_file", ""),
        doc_start_line=int(issue.get("doc_start_line", 1)),
        doc_end_line=int(issue.get("doc_end_line", 1)),
        outdated_excerpt=issue.get("outdated_excerpt", ""),
        explanation=issue.get("explanation", ""),
        suggested_fix=issue.get("suggested_fix", ""),
    )
    return generate_fix_preview(repo_dir(issue.get("repo_id", "")), finding)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "healthy",
        "service": "DocGuard Platform",
        "version": "1.0.0",
        "ai_provider": selected_provider_name(),
        **model_status(),
    }


@app.get("/api/overview")
def get_overview(request: Request) -> dict[str, Any]:
    """Overview metrics: repository count, health score, active issues, recent activity."""
    return get_overview_data(visible_repos(request))


@app.get("/api/repositories")
def get_repositories(request: Request) -> list[dict[str, Any]]:
    session = current_session(request)
    if login_enabled() and session:
        # The maintainer's own repositories from GitHub, so there's nothing to add by hand.
        try:
            refresh_repo_list(session)
        except HTTPException as exc:
            # If GitHub is only briefly unavailable and we have an older list, show that.
            if exc.status_code == 401 or not user_repo_ids(session.login):
                raise exc
        return get_user_repositories(session.login)

    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM repositories ORDER BY health_score DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/sync/status")
def sync_status(request: Request) -> dict[str, Any]:
    session = current_session(request)
    idle = {"state": "idle", "repos": 0, "prs_scanned": 0, "errors": [], "last_synced_at": None}
    return statuses.get(session.login, idle) if session else idle


@app.post("/api/sync")
def sync_now() -> dict[str, bool]:
    sync_wanted.set()
    return {"started": True}


@app.post("/api/repositories")
def add_github_repository(req: AddRepositoryRequest, request: Request) -> dict[str, Any]:
    """Clones a GitHub repository so it can be scanned. Accepts owner/name or a GitHub URL."""
    try:
        repo_id = parse_repo_name(req.repository)
        branch = clone_repo(repo_id, token_for(request))
    except RepoError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    add_repository(repo_id, branch)
    session = current_session(request)
    if session:
        link_user_repository(session.login, repo_id)
    return {"id": repo_id, "full_name": repo_id, "default_branch": branch}


@app.get("/api/reports")
def get_reports(request: Request) -> list[dict[str, Any]]:
    return get_visible_reports(visible_repos(request))


@app.get("/api/reports/{report_id}")
def get_report_details(report_id: str, request: Request) -> dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scan_reports WHERE id = ?", (report_id,))
    report_row = cursor.fetchone()
    if not report_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Report not found")

    require_repo_access(request, report_row["repo_id"])

    cursor.execute("SELECT * FROM findings WHERE report_id = ?", (report_id,))
    finding_rows = cursor.fetchall()
    conn.close()

    findings_list = []
    for f in finding_rows:
        fd = dict(f)
        try:
            fd["evidence"] = json.loads(fd.get("evidence") or "[]")
        except Exception:
            fd["evidence"] = []
        findings_list.append(fd)

    res = dict(report_row)
    res["findings"] = findings_list
    return res


@app.get("/api/issues")
def list_issues(
    request: Request,
    status: Optional[str] = Query(None, description="'open' or 'fixed'"),
    verdict: Optional[str] = Query(None, description="'CONFIRMED_DRIFT' or 'POSSIBLE_DRIFT'"),
) -> list[dict[str, Any]]:
    """Returns all documentation drift issues across scans."""
    return get_all_issues(status=status, verdict=verdict, repo_ids=visible_repos(request))


@app.get("/api/issues/{issue_id}")
def get_issue(issue_id: str, request: Request) -> dict[str, Any]:
    issue = _visible_issue(request, issue_id)

    preview = _preview_for_issue(issue)

    issue["diff_preview"] = preview.diff
    issue["is_applicable"] = preview.is_applicable
    return issue


@app.post("/api/issues/{issue_id}/fix")
def apply_fix_by_id(issue_id: str, request: Request) -> dict[str, Any]:
    _no_local_fixes_when_hosted()
    issue = _visible_issue(request, issue_id)

    preview = _preview_for_issue(issue)
    if not preview.is_applicable:
        raise HTTPException(status_code=400, detail=preview.error_message or "Cannot apply patch to documentation")

    applied = apply_fix(repo_dir(issue.get("repo_id", "")), preview)
    if applied:
        mark_issue_fixed(issue_id)

    return {
        "success": applied,
        "issue_id": issue_id,
        "doc_file": issue.get("doc_file"),
        "message": f"Successfully patched {issue.get('doc_file')} and updated issue status.",
    }


@app.get("/api/autofix/proposals")
def get_autofix_proposals(request: Request) -> list[dict[str, Any]]:
    """Returns all open drift issues with computed before/after patch previews."""
    open_issues = get_all_issues(status="open", repo_ids=visible_repos(request))
    proposals = []
    for issue in open_issues:
        preview = _preview_for_issue(issue)
        proposals.append(
            {
                "issue_id": issue["id"],
                "repo_id": issue["repo_id"],
                "pr_number": issue["pr_number"],
                "default_branch": issue["default_branch"],
                "head_sha": issue["head_sha"],
                "changed_symbol": issue["changed_symbol"],
                "source_file": issue["source_file"],
                "doc_file": issue["doc_file"],
                "doc_start_line": issue["doc_start_line"],
                "outdated_excerpt": issue["outdated_excerpt"],
                "suggested_fix": issue["suggested_fix"],
                "diff": preview.diff,
                "is_applicable": preview.is_applicable,
                "confidence": issue["confidence"],
                "verdict": issue["verdict"],
            }
        )
    return proposals


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    settings = get_settings_data()
    return {
        "settings": settings,
        "system": {
                        "github_webhook_secret_configured": bool(os.getenv("GITHUB_WEBHOOK_SECRET")),
            **model_status(),
            "environment": os.getenv("ENV", "development"),
        },
    }


@app.post("/api/settings")
def update_settings(req: SettingsUpdateRequest) -> dict[str, Any]:
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    update_settings_data(updates)
    return {"status": "success", "settings": get_settings_data()}


@app.post("/api/scan/live")
def run_live_scan(req: ScanRequest, request: Request) -> dict[str, Any]:
    if login_enabled() and not req.repo_id:
        raise HTTPException(status_code=400, detail="Choose a repository to scan")
    repo_id = req.repo_id or local_repo_id()
    if not repository_exists(repo_id):
        raise HTTPException(status_code=404, detail=f"Unknown repository: {repo_id}")
    require_repo_access(request, repo_id)

    try:
        report_id, base_ref, head_ref, scan = scan_repository(
            repo_id,
            token_for(request),
            req.base_ref,
            req.head_ref,
            req.pr_number,
            audit=req.audit,
        )
    except RepoError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Scan failed: {exc}")

    findings_data = [f.to_dict() for f in scan.findings]
    return {
        "report_id": report_id,
        "repo_id": repo_id,
        "base_ref": base_ref,
        "head_ref": head_ref,
        "changes_checked": len(scan.code_changes),
        "total_drifts": scan.total_drifts,
        "confirmed_drifts": scan.confirmed_drifts,
        "possible_drifts": scan.possible_drifts,
        "health_score": scan.health_score,
        "findings": findings_data,
        "markdown_report": scan.generate_markdown_report(),
    }


@app.post("/api/autofix/preview")
def preview_fix(req: AutoFixRequest, request: Request) -> dict[str, Any]:
    require_repo_access(request, req.repo_id or local_repo_id())
    dummy_finding = Finding(
        verdict=Verdict.CONFIRMED_DRIFT,
        confidence=1.0,
        source_file="",
        changed_symbol="",
        doc_file=req.doc_file,
        doc_start_line=1,
        doc_end_line=1,
        outdated_excerpt=req.outdated_excerpt,
        explanation="Auto-fix preview",
        suggested_fix=req.suggested_fix,
    )
    preview = generate_fix_preview(repo_dir(req.repo_id or local_repo_id()), dummy_finding)
    return {
        "doc_file": preview.file_path,
        "is_applicable": preview.is_applicable,
        "diff": preview.diff,
        "error": preview.error_message,
        "updated_text": preview.updated_text,
    }


@app.post("/api/autofix/apply")
def apply_approved_fix(req: AutoFixRequest) -> dict[str, Any]:
    _no_local_fixes_when_hosted()
    dummy_finding = Finding(
        verdict=Verdict.CONFIRMED_DRIFT,
        confidence=1.0,
        source_file="",
        changed_symbol="",
        doc_file=req.doc_file,
        doc_start_line=1,
        doc_end_line=1,
        outdated_excerpt=req.outdated_excerpt,
        explanation="Applying approved fix",
        suggested_fix=req.suggested_fix,
    )
    root = repo_dir(req.repo_id or local_repo_id())
    preview = generate_fix_preview(root, dummy_finding)
    if not preview.is_applicable:
        raise HTTPException(status_code=400, detail=preview.error_message or "Fix cannot be applied")

    success = apply_fix(root, preview)
    if success and req.issue_id:
        mark_issue_fixed(req.issue_id)

    return {
        "success": success,
        "doc_file": req.doc_file,
        "message": f"Successfully updated {req.doc_file} with corrected documentation.",
    }


@app.post("/api/webhook/github")
async def github_webhook(
    request: Request,
    x_github_event: Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None),
) -> dict[str, Any]:
    """GitHub Webhook Receiver with HMAC-SHA256 signature verification."""
    payload_bytes = await request.body()

    # Verify signature if secret configured
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if secret and x_hub_signature_256:
        expected_sig = "sha256=" + hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_sig, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="Invalid HMAC signature")

    try:
        payload = json.loads(payload_bytes.decode())
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed JSON")

    if x_github_event == "pull_request":
        action = payload.get("action")
        pr = payload.get("pull_request", {})
        pr_number = pr.get("number")
        base_sha = pr.get("base", {}).get("sha")
        head_sha = pr.get("head", {}).get("sha")
        repo_name = payload.get("repository", {}).get("full_name", "unknown")

        return {
            "status": "received",
            "action": action,
            "pr_number": pr_number,
            "base_sha": base_sha,
            "head_sha": head_sha,
            "repository": repo_name,
        }

    return {"status": "ignored", "event": x_github_event}
