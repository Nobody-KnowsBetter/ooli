"""GitHub login, with GitHub itself replaced by fake responses."""
import subprocess
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import github_auth, repos, sync
from backend.app.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GITHUB_CLIENT_ID", "test-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("APP_URL", "http://localhost:3000")
    github_auth.sessions.clear()
    sync.repo_list_synced_at.clear()
    return TestClient(app, base_url="http://localhost:3000", follow_redirects=False)


def fake_github(monkeypatch, scope="read:user", token="tok", repo_pages=None, status=200):
    def post(url, headers, data, timeout):
        assert data["client_secret"] == "test-secret"
        return httpx.Response(200, request=httpx.Request("POST", url), json={"access_token": token, "scope": scope} if token else {"error": "bad"})

    def get(url, headers, params, timeout):
        assert headers["Authorization"] == f"Bearer {token}"
        request = httpx.Request("GET", url)
        if url.endswith("/user"):
            return httpx.Response(200, request=request, json={"login": "octo", "name": "Octo", "avatar_url": "a"})
        if url.endswith("/user/repos"):
            pages = repo_pages or [[]]
            return httpx.Response(status, request=request, json=pages[params["page"] - 1])
        return httpx.Response(status, request=request, json=[
            {"number": 7, "title": "Rename flag", "state": "closed", "merged_at": "2026-01-01", "user": {"login": "a"}},
            {"number": 8, "title": "WIP", "state": "open", "merged_at": None, "user": None},
        ])

    monkeypatch.setattr(github_auth.httpx, "post", post)
    monkeypatch.setattr(github_auth.httpx, "get", get)


def log_in(client, private=False):
    res = client.get("/api/auth/login", params={"private": private})
    assert res.status_code == 302
    query = parse_qs(urlparse(res.headers["location"]).query)
    return client.get("/api/auth/callback", params={"code": "c", "state": query["state"][0]}), query


def test_everything_is_open_when_login_is_not_set_up(monkeypatch):
    monkeypatch.setenv("GITHUB_CLIENT_ID", "")
    open_client = TestClient(app, follow_redirects=False)
    assert open_client.get("/api/repositories").status_code == 200
    assert open_client.get("/api/auth/status").json()["login_enabled"] is False
    assert open_client.get("/api/auth/login").headers["location"].endswith("/dashboard")


def test_dashboard_data_needs_login(client):
    assert client.get("/api/repositories").status_code == 401
    assert client.post("/api/scan/live", json={}).status_code == 401
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/auth/status").json()["logged_in"] is False


def test_login_goes_to_the_dashboard_and_opens_the_api(client, monkeypatch):
    fake_github(monkeypatch)
    res, query = log_in(client)
    assert query["scope"] == ["read:user"]
    assert res.headers["location"] == "http://localhost:3000/dashboard"
    assert "httponly" in res.headers["set-cookie"].lower()
    assert "tok" not in res.headers["set-cookie"]
    status = client.get("/api/auth/status").json()
    assert status["logged_in"] is True and status["user"]["login"] == "octo"
    assert status["can_read_private"] is False
    assert "token" not in str(status).lower()
    assert client.get("/api/repositories").status_code == 200


def test_private_access_is_only_requested_when_chosen(client, monkeypatch):
    fake_github(monkeypatch, scope="read:user,repo")
    _, query = log_in(client, private=True)
    assert query["scope"] == ["read:user repo"]
    assert client.get("/api/auth/status").json()["can_read_private"] is True


def test_shared_servers_never_ask_for_private_access(client, monkeypatch):
    monkeypatch.setenv("APP_URL", "https://docguard.example.com")
    res = client.get("/api/auth/login", params={"private": True})
    assert parse_qs(urlparse(res.headers["location"]).query)["scope"] == ["read:user"]


def test_a_forged_callback_is_rejected(client, monkeypatch):
    fake_github(monkeypatch)
    client.get("/api/auth/login")
    res = client.get("/api/auth/callback", params={"code": "c", "state": "forged"})
    assert "login_error=expired" in res.headers["location"]
    assert github_auth.sessions == {}


def test_declined_login_returns_to_the_landing_page(client):
    res = client.get("/api/auth/callback", params={"error": "access_denied"})
    assert res.headers["location"] == "http://localhost:3000/?login_error=denied"


def test_logout_ends_the_session(client, monkeypatch):
    fake_github(monkeypatch)
    log_in(client)
    res = client.post("/api/auth/logout")
    assert "docguard_session" in res.headers["set-cookie"] and "Max-Age=0" in res.headers["set-cookie"]
    assert client.get("/api/repositories").status_code == 401


def repo_json(name):
    return {"full_name": name, "private": False, "default_branch": "main"}


def test_lists_repositories_across_pages(client, monkeypatch):
    first = [repo_json(f"octo/r{i}") for i in range(100)]
    fake_github(monkeypatch, repo_pages=[first, [repo_json("octo/last")]])
    log_in(client)
    names = [r["full_name"] for r in client.get("/api/repositories").json()]
    assert len(names) == 101 and "octo/last" in names


def test_lists_pull_requests_with_merged_state(client, monkeypatch):
    fake_github(monkeypatch)
    log_in(client)
    pulls = client.get("/api/github/pulls", params={"repo": "octo/app"}).json()
    assert pulls[0] == {"number": 7, "title": "Rename flag", "state": "merged", "author": "a"}
    assert pulls[1]["state"] == "open"
    assert client.get("/api/github/pulls", params={"repo": "../bad"}).status_code == 400


def test_expired_github_token_says_so(client, monkeypatch):
    fake_github(monkeypatch, status=401)
    log_in(client)
    res = client.get("/api/repositories")
    assert res.status_code == 401 and "expired" in res.json()["detail"]


def test_token_never_reaches_the_clones_git_config(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    seen = {}
    real_run = subprocess.run

    def run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["env"] = kwargs["env"]
        return real_run(["true"], **{k: v for k, v in kwargs.items() if k != "cwd"})

    monkeypatch.setattr(repos.subprocess, "run", run)
    repos._git("status", token="secret-token")
    assert "secret-token" not in " ".join(seen["cmd"])
    assert seen["env"]["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert "secret-token" not in seen["env"]["GIT_CONFIG_VALUE_0"]


def test_adding_the_env_file_turns_login_on_without_a_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_CLIENT_ID", "")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "")
    env_file = tmp_path / ".env"
    monkeypatch.setattr(github_auth, "ENV_FILE", env_file)
    monkeypatch.setattr(github_auth, "_env_loaded_at", 0.0)
    assert github_auth.login_enabled() is False
    env_file.write_text("GITHUB_CLIENT_ID=new-id\nGITHUB_CLIENT_SECRET=new-secret\n")
    assert github_auth.login_enabled() is True
    assert github_auth.client_id() == "new-id"
