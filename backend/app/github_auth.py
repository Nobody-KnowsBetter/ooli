"""GitHub login, and the GitHub data the dashboard shows after it.

Tokens are kept only in this process's memory, never on disk. Restarting the backend logs everyone out.
If GITHUB_CLIENT_ID isn't set, login is off and the dashboard stays open, so the tool still runs
on a machine that doesn't have our secret, such as CI or a judge's laptop.
"""
from __future__ import annotations

import hmac
import os
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode, urlparse

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse

from backend.app.repos import RepoError, parse_repo_name

SESSION_COOKIE = "docguard_session"
STATE_COOKIE = "docguard_oauth_state"
RETURN_COOKIE = "docguard_return_to"
SESSION_SECONDS = 8 * 60 * 60
MAX_REPO_PAGES = 3

router = APIRouter()

# Tells the background sync to run now, such as right after signing in.
sync_wanted = threading.Event()


@dataclass
class Session:
    token: str
    login: str
    name: str
    avatar_url: str
    can_read_private: bool
    expires_at: float
    can_write: bool = False


sessions: dict[str, Session] = {}


def github_url() -> str:
    return os.getenv("GITHUB_URL", "https://github.com").rstrip("/")


def github_api() -> str:
    return os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/")


ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def _env_file_time() -> float:
    return ENV_FILE.stat().st_mtime if ENV_FILE.exists() else 0.0


_env_loaded_at = _env_file_time()


def _reload_env_if_changed() -> None:
    """Lets someone add their OAuth App's values without restarting the backend."""
    global _env_loaded_at
    changed_at = _env_file_time()
    if changed_at != _env_loaded_at:
        _env_loaded_at = changed_at
        load_dotenv(ENV_FILE, override=True)


def client_id() -> str:
    return os.getenv("GITHUB_CLIENT_ID", "")


def client_secret() -> str:
    return os.getenv("GITHUB_CLIENT_SECRET", "")


def login_enabled() -> bool:
    _reload_env_if_changed()
    return bool(client_id() and client_secret())


def app_url() -> str:
    return os.getenv("APP_URL", "http://localhost:3000").rstrip("/")


def private_repos_allowed() -> bool:
    """Everyone on a server shares the dashboard's data, so private repos are for local use only."""
    return urlparse(app_url()).hostname in {"localhost", "127.0.0.1"}


def safe_return_path(path: str) -> bool:
    """Only pages inside the dashboard, so a crafted link can't send someone to another site."""
    return path == "/dashboard" or (path.startswith("/dashboard/") and "//" not in path and "\\" not in path)


def current_session(request: Request) -> Optional[Session]:
    session = sessions.get(request.cookies.get(SESSION_COOKIE, ""))
    if session and session.expires_at < time.time():
        sessions.pop(request.cookies.get(SESSION_COOKIE, ""), None)
        return None
    return session


def live_sessions() -> list[Session]:
    """One session per person, since two browsers of the same user need only one sync."""
    now = time.time()
    return list({s.login: s for s in sessions.values() if s.expires_at > now}.values())


def token_for(request: Request) -> Optional[str]:
    session = current_session(request)
    return session.token if session else None


def _github_get(path: str, token: str, **params: Any) -> httpx.Response:
    return httpx.get(
        f"{github_api()}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        params=params,
        timeout=15.0,
    )


def _login_failed(reason: str) -> RedirectResponse:
    response = RedirectResponse(f"{app_url()}/?login_error={reason}", status_code=302)
    response.delete_cookie(STATE_COOKIE)
    return response


def _set_cookie(response: RedirectResponse, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=app_url().startswith("https://"),
    )


@router.get("/api/auth/status")
def auth_status(request: Request) -> dict[str, Any]:
    session = current_session(request)
    return {
        "login_enabled": login_enabled(),
        "private_repos_allowed": private_repos_allowed(),
        "logged_in": session is not None,
        "user": {"login": session.login, "name": session.name, "avatar_url": session.avatar_url}
        if session
        else None,
        "can_read_private": bool(session and session.can_read_private),
        "can_write": bool(session and session.can_write),
    }


@router.get("/api/auth/login")
def login(private: bool = False, write: bool = False, next: str = "") -> RedirectResponse:
    if not login_enabled():
        return RedirectResponse(f"{app_url()}/dashboard", status_code=302)

    state = secrets.token_urlsafe(32)
    # GitHub has no read-only permission for private code, so we ask for "repo" only when the user chooses it.
    private = private and private_repos_allowed()
    scope = "read:user repo" if private else "read:user"
    # Writing is only asked for when someone chooses a feature that opens a pull request.
    if write:
        scope += " workflow" if private else " public_repo workflow"
    query = urlencode(
        {
            "client_id": client_id(),
            "redirect_uri": f"{app_url()}/api/auth/callback",
            "scope": scope,
            "state": state,
        }
    )
    response = RedirectResponse(f"{github_url()}/login/oauth/authorize?{query}", status_code=302)
    _set_cookie(response, STATE_COOKIE, state, 600)
    if safe_return_path(next):
        _set_cookie(response, RETURN_COOKIE, next, 600)
    return response


@router.get("/api/auth/callback")
def callback(request: Request, code: str = "", state: str = "", error: str = "") -> RedirectResponse:
    if error:
        return _login_failed("denied")

    expected = request.cookies.get(STATE_COOKIE, "")
    if not code or not expected or not hmac.compare_digest(state, expected):
        return _login_failed("expired")

    try:
        token_response = httpx.post(
            f"{github_url()}/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": client_id(),
                "client_secret": client_secret(),
                "code": code,
                "redirect_uri": f"{app_url()}/api/auth/callback",
            },
            timeout=15.0,
        )
        token_response.raise_for_status()
        token_data = token_response.json()
        token = token_data.get("access_token")
        if not token:
            return _login_failed("rejected")

        user_response = _github_get("/user", token)
        user_response.raise_for_status()
        user = user_response.json()
    except (httpx.HTTPError, ValueError):
        return _login_failed("unavailable")

    scopes = set(token_data.get("scope", "").replace(",", " ").split())
    session_id = secrets.token_urlsafe(32)
    sessions[session_id] = Session(
        token=token,
        login=user.get("login", ""),
        name=user.get("name") or user.get("login", ""),
        avatar_url=user.get("avatar_url", ""),
        can_read_private="repo" in scopes,
        can_write=bool(scopes & {"repo", "public_repo"}) and "workflow" in scopes,
        expires_at=time.time() + SESSION_SECONDS,
    )

    return_path = request.cookies.get(RETURN_COOKIE, "")
    target = return_path if safe_return_path(return_path) else "/dashboard"
    response = RedirectResponse(f"{app_url()}{target}", status_code=302)
    response.delete_cookie(STATE_COOKIE)
    response.delete_cookie(RETURN_COOKIE)
    _set_cookie(response, SESSION_COOKIE, session_id, SESSION_SECONDS)
    sync_wanted.set()
    return response


@router.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    sessions.pop(request.cookies.get(SESSION_COOKIE, ""), None)
    response.delete_cookie(SESSION_COOKIE)
    return {"logged_out": True}


def _require_token(request: Request) -> str:
    token = token_for(request)
    if not token:
        raise HTTPException(status_code=401, detail="Log in with GitHub first")
    return token


def _github_json(path: str, token: str, **params: Any) -> Any:
    try:
        response = _github_get(path, token, **params)
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Could not reach GitHub")
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Your GitHub login expired. Log in again.")
    if response.status_code == 403:
        raise HTTPException(status_code=429, detail="GitHub's rate limit was reached. Try again soon.")
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="GitHub couldn't find that repository")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="GitHub returned an error")
    return response.json()


def list_user_repos(token: str) -> list[dict[str, Any]]:
    """The repositories this user can access, most recently pushed first."""
    repos: list[dict[str, Any]] = []
    for page in range(1, MAX_REPO_PAGES + 1):
        batch = _github_json("/user/repos", token, per_page=100, sort="pushed", page=page)
        repos.extend(batch)
        if len(batch) < 100:
            break
    return [
        {
            "full_name": repo["full_name"],
            "description": repo.get("description") or "",
            "private": repo.get("private", False),
            "language": repo.get("language") or "",
            "default_branch": repo.get("default_branch", "main"),
            "pushed_at": repo.get("pushed_at") or "",
        }
        for repo in repos
    ]


def list_open_pulls(repo_id: str, token: str) -> list[dict[str, Any]]:
    pulls = _github_json(f"/repos/{repo_id}/pulls", token, state="open", sort="updated", direction="desc", per_page=30)
    return [
        {"number": pull["number"], "title": pull.get("title", ""), "head_sha": pull["head"]["sha"]}
        for pull in pulls
    ]


@router.get("/api/github/pulls")
def list_pull_requests(request: Request, repo: str = Query(...)) -> list[dict[str, Any]]:
    """A repository's most recently updated pull requests, open and closed."""
    token = _require_token(request)
    try:
        repo_id = parse_repo_name(repo)
    except RepoError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    pulls = _github_json(f"/repos/{repo_id}/pulls", token, state="all", sort="updated", direction="desc", per_page=30)
    return [
        {
            "number": pull["number"],
            "title": pull.get("title", ""),
            "state": "merged" if pull.get("merged_at") else pull.get("state", ""),
            "author": (pull.get("user") or {}).get("login", ""),
        }
        for pull in pulls
    ]
