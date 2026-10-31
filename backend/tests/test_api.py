"""Tests for FastAPI backend endpoints."""
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.repos import local_repo_id

client = TestClient(app)


def test_root_only_points_to_the_dashboard():
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["dashboard"] == "http://localhost:3000"
    assert "text/html" not in res.headers["content-type"]


def test_api_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "DocGuard" in data["service"]


def test_api_overview():
    res = client.get("/api/overview")
    assert res.status_code == 200
    data = res.json()
    assert "repository_count" in data
    assert "avg_health_score" in data
    assert "total_active_drifts" in data


def test_api_repositories():
    res = client.get("/api/repositories")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["full_name"] == local_repo_id()


def test_api_scan_live():
    res = client.post("/api/scan/live", json={"base_ref": "HEAD~1", "head_ref": "HEAD"})
    assert res.status_code == 200
    data = res.json()
    assert "report_id" in data
    assert "health_score" in data
    assert "findings" in data
    assert "markdown_report" in data


def test_api_issues_and_detail():
    # Trigger scan first to guarantee findings in db
    client.post("/api/scan/live", json={"base_ref": "HEAD~1", "head_ref": "HEAD"})
    res = client.get("/api/issues")
    assert res.status_code == 200
    issues = res.json()
    assert isinstance(issues, list)

    if issues:
        issue_id = issues[0]["id"]
        res_detail = client.get(f"/api/issues/{issue_id}")
        assert res_detail.status_code == 200
        assert res_detail.json()["id"] == issue_id


def test_api_autofix_proposals():
    res = client.get("/api/autofix/proposals")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_api_settings_get_and_update():
    res = client.get("/api/settings")
    assert res.status_code == 200
    data = res.json()
    assert "settings" in data
    assert "system" in data

    res_post = client.post("/api/settings", json={"ai_provider": "heuristic", "confidence_threshold": "0.80"})
    assert res_post.status_code == 200
    assert res_post.json()["settings"]["confidence_threshold"] == "0.80"


def test_api_reports_list_and_detail():
    res = client.get("/api/reports")
    assert res.status_code == 200
    reports = res.json()
    assert len(reports) >= 1
    report_id = reports[0]["id"]

    res_detail = client.get(f"/api/reports/{report_id}")
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert detail["id"] == report_id
    assert "findings" in detail


def test_api_webhook_unverified_rejection():
    import os
    os.environ["GITHUB_WEBHOOK_SECRET"] = "super-secret-key"
    try:
        res = client.post(
            "/api/webhook/github",
            headers={"x-github-event": "pull_request", "x-hub-signature-256": "sha256=invalid"},
            json={"action": "opened"},
        )
        assert res.status_code == 401
    finally:
        del os.environ["GITHUB_WEBHOOK_SECRET"]
