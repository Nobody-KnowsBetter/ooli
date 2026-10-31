"""DocGuard FastAPI Application."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.app.analyzer.models import Finding, Verdict
from backend.app.analyzer.pipeline import run_analysis
from backend.app.autofix.patcher import apply_fix, generate_fix_preview
from backend.app.database.db import (
    get_all_issues,
    get_db_connection,
    get_issue_by_id,
    get_overview_data,
    get_settings_data,
    init_db,
    mark_issue_fixed,
    save_scan_report,
    update_settings_data,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Ensure database tables exist immediately
init_db()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    init_db()
    yield


app = FastAPI(
    title="DocGuard Documentation Intelligence API",
    description="Detects, explains, and fixes documentation drift using AST and AI reasoning.",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for Next.js dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount frontend public static files if present
FRONTEND_DIR = PROJECT_ROOT / "frontend" / "public"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def serve_dashboard():
        return FileResponse(str(FRONTEND_DIR / "index.html"))


class ScanRequest(BaseModel):
    base_ref: str = "HEAD~1"
    head_ref: str = "HEAD"
    repo_id: str = "krishgarg-code/JavaBasicPrograms1"
    pr_number: Optional[int] = None


class AutoFixRequest(BaseModel):
    doc_file: str
    outdated_excerpt: str
    suggested_fix: str
    issue_id: Optional[str] = None


class SettingsUpdateRequest(BaseModel):
    ai_provider: Optional[str] = None
    confidence_threshold: Optional[str] = None
    auto_comment: Optional[str] = None
    monitored_branches: Optional[str] = None


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "healthy",
        "service": "DocGuard Platform",
        "version": "1.0.0",
        "ai_provider": os.getenv("DOCGUARD_AI_PROVIDER", "heuristic"),
    }


@app.get("/api/overview")
def get_overview() -> dict[str, Any]:
    """Overview metrics: repository count, health score, active issues, recent activity."""
    return get_overview_data()


@app.get("/api/repositories")
def get_repositories() -> list[dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM repositories ORDER BY health_score DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/reports")
def get_reports() -> list[dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM scan_reports
        ORDER BY created_at DESC
        LIMIT 20
    """
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/reports/{report_id}")
def get_report_details(report_id: str) -> dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scan_reports WHERE id = ?", (report_id,))
    report_row = cursor.fetchone()
    if not report_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Report not found")

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
    status: Optional[str] = Query(None, description="'open' or 'fixed'"),
    verdict: Optional[str] = Query(None, description="'CONFIRMED_DRIFT' or 'POSSIBLE_DRIFT'"),
) -> list[dict[str, Any]]:
    """Returns all documentation drift issues across scans."""
    return get_all_issues(status=status, verdict=verdict)


@app.get("/api/issues/{issue_id}")
def get_issue(issue_id: str) -> dict[str, Any]:
    issue = get_issue_by_id(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    # Generate unified diff preview
    dummy_finding = Finding(
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
    preview = generate_fix_preview(PROJECT_ROOT, dummy_finding)

    issue["diff_preview"] = preview.diff
    issue["is_applicable"] = preview.is_applicable
    return issue


@app.post("/api/issues/{issue_id}/fix")
def apply_fix_by_id(issue_id: str) -> dict[str, Any]:
    issue = get_issue_by_id(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    dummy_finding = Finding(
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
    preview = generate_fix_preview(PROJECT_ROOT, dummy_finding)
    if not preview.is_applicable:
        raise HTTPException(status_code=400, detail="Cannot apply patch to documentation")

    applied = apply_fix(PROJECT_ROOT, preview)
    if applied:
        mark_issue_fixed(issue_id)

    return {
        "success": applied,
        "issue_id": issue_id,
        "doc_file": issue.get("doc_file"),
        "message": f"Successfully patched {issue.get('doc_file')} and updated issue status.",
    }


@app.get("/api/autofix/proposals")
def get_autofix_proposals() -> list[dict[str, Any]]:
    """Returns all open drift issues with computed before/after patch previews."""
    open_issues = get_all_issues(status="open")
    proposals = []
    for issue in open_issues:
        dummy_finding = Finding(
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
        preview = generate_fix_preview(PROJECT_ROOT, dummy_finding)
        proposals.append(
            {
                "issue_id": issue["id"],
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
            "github_token_configured": bool(os.getenv("GITHUB_TOKEN")),
            "github_webhook_secret_configured": bool(os.getenv("GITHUB_WEBHOOK_SECRET")),
            "gemini_api_key_configured": bool(os.getenv("GEMINI_API_KEY")),
            "openai_api_key_configured": bool(os.getenv("OPENAI_API_KEY")),
            "environment": os.getenv("ENV", "development"),
        },
    }


@app.post("/api/settings")
def update_settings(req: SettingsUpdateRequest) -> dict[str, Any]:
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    update_settings_data(updates)
    return {"status": "success", "settings": get_settings_data()}


@app.post("/api/scan/live")
def run_live_scan(req: ScanRequest) -> dict[str, Any]:
    report_id = f"report-{uuid.uuid4().hex[:8]}"
    try:
        scan = run_analysis(repo_root=PROJECT_ROOT, base_ref=req.base_ref, head_ref=req.head_ref)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Scan failed: {exc}")

    findings_data = [f.to_dict() for f in scan.findings]
    save_scan_report(
        report_id=report_id,
        repo_id=req.repo_id,
        base_sha=req.base_ref,
        head_sha=req.head_ref,
        pr_number=req.pr_number,
        total_drifts=scan.total_drifts,
        confirmed_drifts=scan.confirmed_drifts,
        possible_drifts=scan.possible_drifts,
        health_score=scan.health_score,
        findings=findings_data,
    )

    return {
        "report_id": report_id,
        "base_ref": req.base_ref,
        "head_ref": req.head_ref,
        "total_drifts": scan.total_drifts,
        "confirmed_drifts": scan.confirmed_drifts,
        "possible_drifts": scan.possible_drifts,
        "health_score": scan.health_score,
        "findings": findings_data,
        "markdown_report": scan.generate_markdown_report(),
    }


@app.post("/api/autofix/preview")
def preview_fix(req: AutoFixRequest) -> dict[str, Any]:
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
    preview = generate_fix_preview(PROJECT_ROOT, dummy_finding)
    return {
        "doc_file": preview.file_path,
        "is_applicable": preview.is_applicable,
        "diff": preview.diff,
        "error": preview.error_message,
        "updated_text": preview.updated_text,
    }


@app.post("/api/autofix/apply")
def apply_approved_fix(req: AutoFixRequest) -> dict[str, Any]:
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
    preview = generate_fix_preview(PROJECT_ROOT, dummy_finding)
    if not preview.is_applicable:
        raise HTTPException(status_code=400, detail=preview.error_message or "Fix cannot be applied")

    success = apply_fix(PROJECT_ROOT, preview)
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
