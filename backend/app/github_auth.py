"""GitHub login, and the GitHub data the dashboard shows after it.

Tokens are kept only in this process's memory, never on disk. Restarting the backend logs everyone out.
If GITHUB_CLIENT_ID isn't set, login is off and the dashboard stays open, so the tool still runs
on a machine that doesn't have our secret, such as CI or a judge's laptop.
"""
from __future__ import annotations

import hmac
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from backend.app.repos import RepoError, parse_repo_name

GITHUB_URL = "https://github.com"
GITHUB_API = "https://api.github.com"
SESSION_COOKIE = "docguard_session"
STATE_COOKIE = "docguard_oauth_state"
SESSION_SECONDS = 8 * 60 * 60
MAX_REPO_PAGES = 3

router = APIRouter()


@dataclass
class Session:
    token: str
    login: str
    name: str
    avatar_url: str
    can_read_private: bool
    expires_at: float


sessions: dict[str, Session] = {}


def client_id() -> str:
    return os.getenv("GITHUB_CLIENT_ID", "")


def client_secret() -> str:
    return os.getenv("GITHUB_CLIENT_SECRET", "")


def login_enabled() -> bool:
    return bool(client_id() and client_secret())


def app_url() -> str:
    return os.getenv("APP_URL", "http://localhost:3000").rstrip("/")


def private_repos_allowed() -> bool:
    """Everyone on a server shares the dashboard's data, so private repos are for local use only."""
    return urlparse(app_url()).hostname in {"localhost", "127.0.0.1"}


def current_session(request: Request) -> Optional[Session]:
    session = sessions.get(request.cookies.get(SESSION_COOKIE, ""))
    if session and session.expires_at < time.time():
        sessions.pop(request.cookies.get(SESSION_COOKIE, ""), None)
        return None
    return session


def token_for(request: Request) -> Optional[str]:
    session = current_session(request)
    return session.token if session else None


def _github_get(path: str, token: str, **params: Any) -> httpx.Response:
    return httpx.get(
        f"{GITHUB_API}{path}",
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
    }


@router.get("/api/auth/login")
def login(private: bool = False) -> RedirectResponse:
    if not login_enabled():
        return RedirectResponse(f"{app_url()}/dashboard", status_code=302)

    state = secrets.token_urlsafe(32)
    # GitHub has no read-only permission for private code, so we ask for "repo" only when the user chooses it.
    scope = "read:user repo" if private and private_repos_allowed() else "read:user"
    query = urlencode(
        {
            "client_id": client_id(),
            "redirect_uri": f"{app_url()}/api/auth/callback",
            "scope": scope,
            "state": state,
        }
    )
    response = RedirectResponse(f"{GITHUB_URL}/login/oauth/authorize?{query}", status_code=302)
    _set_cookie(response, STATE_COOKIE, state, 600)
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
            f"{GITHUB_URL}/login/oauth/access_token",
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

    session_id = secrets.token_urlsafe(32)
    sessions[session_id] = Session(
        token=token,
        login=user.get("login", ""),
        name=user.get("name") or user.get("login", ""),
        avatar_url=user.get("avatar_url", ""),
        can_read_private="repo" in token_data.get("scope", "").replace(",", " ").split(),
        expires_at=time.time() + SESSION_SECONDS,
    )

    response = RedirectResponse(f"{app_url()}/dashboard", status_code=302)
    response.delete_cookie(STATE_COOKIE)
    _set_cookie(response, SESSION_COOKIE, session_id, SESSION_SECONDS)
    return response


@router.post("/api/auth/logout")
def logout(request: Request) -> dict[str, bool]:
    sessions.pop(request.cookies.get(SESSION_COOKIE, ""), None)
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


@router.get("/api/github/repos")
def list_github_repos(request: Request) -> list[dict[str, Any]]:
    """The repositories this user can import, most recently pushed first."""
    token = _require_token(request)
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
