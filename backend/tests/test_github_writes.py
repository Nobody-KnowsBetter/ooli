"""One-click fix pull requests and Action setup, against a fake GitHub that remembers what it was asked."""
import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import github_auth, github_writes, sync
from backend.app.database import db
from backend.app.github_auth import Session
from backend.app.main import app


class FakeGithub:
    def __init__(self, files=None, write_status=None):
        self.files = files or {}
        self.write_status = write_status
        self.calls = []
        self.pulls = []

    def __call__(self, method, url, headers, timeout, **kwargs):
        path = url.split("api.github.com", 1)[1]
        self.calls.append((method, path))
        body = kwargs.get("json")
        request = httpx.Request(method, url)

        def reply(status, data=None):
            return httpx.Response(status, request=request, json=data if data is not None else {})

        if method != "GET" and self.write_status:
            return reply(self.write_status)
        if method == "GET" and path == "/repos/octo/app":
            return reply(200, {"default_branch": "main"})
        if "/git/ref/heads/" in path:
            return reply(200, {"object": {"sha": "abc"}})
        if method == "POST" and path.endswith("/git/refs"):
            self.branch = body["ref"]
            return reply(201, {})
        if method == "DELETE":
            return reply(204)
        if "/contents/" in path:
            name = path.split("/contents/", 1)[1]
            if method == "GET":
                if name not in self.files:
                    return reply(404)
                return reply(200, {"sha": "s", "content": base64.b64encode(self.files[name].encode()).decode()})
            self.files[name] = base64.b64decode(body["content"]).decode()
            return reply(201, {})
        if method == "POST" and path.endswith("/pulls"):
            self.pulls.append(body)
            return reply(201, {"html_url": f"https://github.com/octo/app/pull/{len(self.pulls) + 10}"})
        if method == "GET" and "/pulls/" in path:
            return reply(200, self.pull_info)
        return reply(404)

    pull_info = {"state": "closed", "head": {"ref": "x", "repo": {"full_name": "octo/app"}}}


def issue(line=1, sentence="Use --timeout.", fix="Use --deadline.", pr=None, doc="README.md"):
    return {
        "doc_file": doc, "doc_start_line": line, "outdated_excerpt": sentence,
        "suggested_fix": fix, "pr_number": pr,
    }


@pytest.fixture
def fake(monkeypatch):
    github = FakeGithub({"README.md": "# Usage\nUse --timeout.\nSpeed is 120.\n"})
    monkeypatch.setattr(github_writes.httpx, "request", github)
    return github


def test_fix_pr_corrects_every_sentence_in_one_commit_per_file(fake):
    url = github_writes.create_fix_pull_request(
        "octo/app", "t", [issue(2), issue(3, "Speed is 120.", "Speed is 150.")]
    )
    assert url.endswith("/pull/11")
    assert fake.files["README.md"] == "# Usage\nUse --deadline.\nSpeed is 150.\n"
    assert fake.pulls[0]["base"] == "main"
    assert fake.pulls[0]["title"] == "Fix 2 outdated doc sentences"
    assert sum(1 for method, _ in fake.calls if method == "PUT") == 1


def test_fix_finds_the_sentence_if_its_line_moved(fake):
    github_writes.create_fix_pull_request("octo/app", "t", [issue(99)])
    assert "Use --deadline." in fake.files["README.md"]


def test_only_the_reported_line_changes(fake):
    fake.files["README.md"] = "Use --timeout.\nUse --timeout.\n"
    github_writes.create_fix_pull_request("octo/app", "t", [issue(2)])
    assert fake.files["README.md"] == "Use --timeout.\nUse --deadline.\n"


def test_nothing_to_fix_removes_the_branch(fake):
    fake.files["README.md"] = "Already fixed.\n"
    with pytest.raises(github_writes.GithubWriteError, match="already changed"):
        github_writes.create_fix_pull_request("octo/app", "t", [issue()])
    assert any(method == "DELETE" for method, _ in fake.calls)
    assert fake.pulls == []


def test_issues_without_text_are_refused(fake):
    with pytest.raises(github_writes.GithubWriteError, match="by hand"):
        github_writes.create_fix_pull_request("octo/app", "t", [issue(fix="")])


def test_no_write_access_says_what_to_do(monkeypatch):
    github = FakeGithub({"README.md": "x"}, write_status=403)
    monkeypatch.setattr(github_writes.httpx, "request", github)
    with pytest.raises(github_writes.GithubWriteError, match="write access"):
        github_writes.create_fix_pull_request("octo/app", "t", [issue()])


def test_fix_for_an_open_pr_goes_to_that_prs_branch(fake):
    fake.pull_info = {"state": "open", "head": {"ref": "rename-flag", "repo": {"full_name": "octo/app"}}}
    github_writes.create_fix_pull_request("octo/app", "t", [issue(2, pr=7)])
    assert fake.pulls[0]["base"] == "rename-flag"


def test_fix_for_a_fork_pr_goes_to_the_main_branch(fake):
    fake.pull_info = {"state": "open", "head": {"ref": "rename", "repo": {"full_name": "someone/app"}}}
    github_writes.create_fix_pull_request("octo/app", "t", [issue(2, pr=7)])
    assert fake.pulls[0]["base"] == "main"


def test_action_setup_opens_a_pr_with_the_workflow(fake):
    result = github_writes.add_action_pull_request("octo/app", "t")
    assert result["already_installed"] is False
    assert "Nobody-KnowsBetter/ooli@main" in fake.files[github_writes.WORKFLOW_PATH]
    assert "pull_request_target" in fake.files[github_writes.WORKFLOW_PATH]
    assert fake.pulls[0]["base"] == "main"


def test_action_setup_does_nothing_if_already_there(fake):
    fake.files[github_writes.WORKFLOW_PATH] = "exists"
    result = github_writes.add_action_pull_request("octo/app", "t")
    assert result["already_installed"] is True
    assert fake.pulls == []


def test_the_workflow_never_checks_out_or_runs_pr_code():
    # pull_request_target has a write token, so running a PR's code here would be dangerous.
    assert "ref:" not in github_writes.WORKFLOW_FILE
    assert "run:" not in github_writes.WORKFLOW_FILE


@pytest.fixture
def signed_in(monkeypatch, fake):
    monkeypatch.setenv("GITHUB_CLIENT_ID", "id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "secret")
    conn = db.get_db_connection()
    for table in ("findings", "scan_reports", "user_repositories"):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()
    db.add_repository("octo/app", "main")
    db.link_user_repository("octo", "octo/app")
    db.save_scan_report(
        "r1", "octo/app", "a", "b", None, 1, 1, 0, 82.0,
        [{"verdict": "CONFIRMED_DRIFT", "confidence": 0.9, "doc_file": "README.md", "doc_start_line": 2, "doc_end_line": 2,
          "changed_symbol": "--timeout", "source_file": "cli.py", "outdated_excerpt": "Use --timeout.",
          "suggested_fix": "Use --deadline.", "explanation": "", "code_diff": "", "evidence": []}],
    )
    sync.repo_list_synced_at["octo"] = sync.repo_list_synced_at["mona"] = 9e12
    github_auth.sessions.clear()
    github_auth.sessions["writer"] = Session("t", "octo", "Octo", "", False, 9e12, can_write=True)
    github_auth.sessions["reader"] = Session("t", "octo", "Octo", "", False, 9e12)
    github_auth.sessions["other"] = Session("t", "mona", "Mona", "", False, 9e12, can_write=True)
    yield
    github_auth.sessions.clear()
    sync.repo_list_synced_at.clear()


def client(cookie):
    return TestClient(app, cookies={github_auth.SESSION_COOKIE: cookie}, follow_redirects=False)


def test_api_opens_a_fix_pr_and_remembers_it(signed_in):
    issue_id = client("writer").get("/api/issues").json()[0]["id"]
    res = client("writer").post("/api/fixes/pull-request", json={"issue_ids": [issue_id]})
    assert res.status_code == 200
    proposals = client("writer").get("/api/autofix/proposals").json()
    assert proposals[0]["fix_pr_url"] == res.json()["url"]


def test_api_asks_for_write_access_first(signed_in):
    issue_id = client("reader").get("/api/issues").json()[0]["id"]
    res = client("reader").post("/api/fixes/pull-request", json={"issue_ids": [issue_id]})
    assert res.status_code == 403 and res.json()["detail"] == "needs_write_access"
    assert client("reader").post("/api/repositories/action", json={"repo_id": "octo/app"}).status_code == 403


def test_api_refuses_another_users_repo(signed_in):
    issue_id = client("writer").get("/api/issues").json()[0]["id"]
    assert client("other").post("/api/fixes/pull-request", json={"issue_ids": [issue_id]}).status_code == 404
    assert client("other").post("/api/repositories/action", json={"repo_id": "octo/app"}).status_code == 404


def test_merging_the_fix_pr_resolves_the_issue(signed_in, fake, monkeypatch):
    issue_id = client("writer").get("/api/issues").json()[0]["id"]
    client("writer").post("/api/fixes/pull-request", json={"issue_ids": [issue_id]})
    monkeypatch.setattr(sync, "list_user_repos", lambda token: [{
        "full_name": "octo/app", "description": "", "private": False, "language": "",
        "default_branch": "main", "pushed_at": "2001-01-01T00:00:00Z"}])
    fake.pull_info = {"merged_at": "2026-01-01", "state": "closed", "head": {"ref": "x", "repo": {"full_name": "octo/app"}}}
    sync.sync_session(github_auth.sessions["writer"])
    assert client("writer").get("/api/issues?status=open").json() == []


@pytest.mark.parametrize("path, allowed", [
    ("/dashboard/autofix", True), ("/dashboard", True),
    ("https://evil.example", False), ("//evil.example", False), ("/dashboard//evil", False), ("/other", False),
])
def test_return_links_stay_inside_the_dashboard(path, allowed):
    assert github_auth.safe_return_path(path) is allowed


def test_write_login_asks_for_write_scopes_and_remembers_the_page(signed_in):
    res = client("writer").get("/api/auth/login", params={"write": True, "next": "/dashboard/autofix"})
    assert "public_repo" in res.headers["location"] and "workflow" in res.headers["location"]
    assert "docguard_return_to=/dashboard/autofix" in res.headers["set-cookie"].replace('"', "")
