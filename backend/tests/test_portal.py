"""The portal: repositories appear by themselves, open PRs get scanned, and users see only their own data."""
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import github_auth, repos, sync
from backend.app.ai.intelligence import HeuristicAIProvider, QwenProvider
from backend.app.database import db
from backend.app.github_auth import Session
from backend.app.main import app


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def github(tmp_path, monkeypatch):
    """A local stand-in for github.com: octo/app.git with PR #7, which renames a documented flag."""
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init", "-q", "-b", "main")
    (work / "cli.py").write_text('parser.add_argument("--timeout")\n')
    (work / "README.md").write_text("Use --timeout to stop slow jobs.\n")
    git(work, "add", ".")
    git(work, "commit", "-qm", "start")
    git(work, "switch", "-qc", "rename")
    (work / "cli.py").write_text('parser.add_argument("--deadline")\n')
    git(work, "commit", "-qam", "rename flag")
    head = git(work, "rev-parse", "HEAD")
    git(work, "switch", "-q", "main")

    bare = tmp_path / "remote" / "octo" / "app.git"
    bare.parent.mkdir(parents=True)
    git(tmp_path, "clone", "-q", "--bare", str(work), str(bare))
    git(bare, "update-ref", "refs/pull/7/head", head)

    monkeypatch.setenv("GITHUB_URL", f"file://{tmp_path / 'remote'}")
    monkeypatch.setattr(repos, "CLONES_DIR", tmp_path / "clones")
    monkeypatch.setattr(sync, "list_user_repos", lambda token: [repo_row("octo/app")])
    monkeypatch.setattr(
        sync, "list_open_pulls", lambda repo, token: [{"number": 7, "title": "Rename flag", "head_sha": head}]
    )
    sync.statuses.clear()
    sync.repo_list_synced_at.clear()
    # Commits made in the same second share a hash, so each test needs an empty database.
    conn = db.get_db_connection()
    for table in ("findings", "scan_reports", "user_repositories"):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()
    return {"work": work, "bare": bare, "head": head}


def repo_row(name: str) -> dict:
    return {
        "full_name": name, "description": "", "private": False, "language": "Python",
        "default_branch": "main", "pushed_at": "2999-01-01T00:00:00Z",
    }


def session(login: str = "octo") -> Session:
    return Session("tok", login, login, "", False, 9e12)


def issues_for(repo: str) -> list:
    return [i for i in db.get_all_issues(status="open") if i["repo_id"] == repo]


def test_sync_lists_repos_and_scans_open_prs_without_being_asked(github):
    status = sync.sync_session(session())
    assert status["errors"] == []
    assert status["prs_scanned"] == 1
    assert status["last_synced_at"]

    listed = db.get_user_repositories("octo")
    assert listed[0]["id"] == "octo/app"
    assert listed[0]["open_prs"] == 1
    assert listed[0]["open_issues"] == 1

    issue = issues_for("octo/app")[0]
    assert issue["pr_number"] == 7
    assert issue["pr_title"] == "Rename flag"
    assert issue["outdated_excerpt"] == "Use --timeout to stop slow jobs."
    assert issue["default_branch"] == "main"


def test_the_same_commit_is_not_scanned_twice(github):
    sync.sync_session(session())
    assert sync.sync_session(session())["prs_scanned"] == 0
    assert len(issues_for("octo/app")) == 1


def test_fixing_the_doc_in_the_pr_resolves_the_issue(github):
    sync.sync_session(session())
    work = github["work"]
    git(work, "switch", "-q", "rename")
    (work / "README.md").write_text("Use --deadline to stop slow jobs.\n")
    git(work, "commit", "-qam", "fix docs")
    head = git(work, "rev-parse", "HEAD")
    git(work, "push", "-q", str(github["bare"]), f"{head}:refs/pull/7/head")

    sync.list_open_pulls = lambda repo, token: [{"number": 7, "title": "Rename flag", "head_sha": head}]
    assert sync.sync_session(session())["prs_scanned"] == 1
    assert issues_for("octo/app") == []


def test_repos_removed_on_github_disappear_from_the_list(github, monkeypatch):
    sync.sync_session(session())
    monkeypatch.setattr(sync, "list_user_repos", lambda token: [])
    sync.sync_session(session())
    assert db.get_user_repositories("octo") == []


def test_one_broken_repo_does_not_stop_the_others(github, monkeypatch):
    monkeypatch.setattr(sync, "list_user_repos", lambda token: [repo_row("octo/missing"), repo_row("octo/app")])
    monkeypatch.setattr(
        sync,
        "list_open_pulls",
        lambda repo, token: [{"number": 7, "title": "t", "head_sha": github["head"]}],
    )
    status = sync.sync_session(session())
    assert status["errors"] == ["octo/missing"]
    assert status["prs_scanned"] == 1


def test_inactive_repos_are_not_cloned(github, monkeypatch):
    old = {**repo_row("octo/app"), "pushed_at": "2001-01-01T00:00:00Z"}
    monkeypatch.setattr(sync, "list_user_repos", lambda token: [old])
    assert sync.sync_session(session())["prs_scanned"] == 0
    assert not repos.CLONES_DIR.exists()


@pytest.fixture
def two_users(github, monkeypatch):
    monkeypatch.setenv("GITHUB_CLIENT_ID", "id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "secret")
    github_auth.sessions.clear()
    sync.sync_session(session("octo"))
    github_auth.sessions["octo-cookie"] = session("octo")
    github_auth.sessions["mona-cookie"] = session("mona")
    sync.sync_user_repositories("mona", [repo_row("mona/other")])
    sync.repo_list_synced_at["octo"] = sync.repo_list_synced_at["mona"] = 9e12
    yield
    github_auth.sessions.clear()
    sync.repo_list_synced_at.clear()


def client_for(cookie: str) -> TestClient:
    return TestClient(app, cookies={github_auth.SESSION_COOKIE: cookie})


def test_a_maintainer_sees_their_own_data(two_users):
    octo = client_for("octo-cookie")
    assert [r["id"] for r in octo.get("/api/repositories").json()] == ["octo/app"]
    assert octo.get("/api/overview").json()["total_active_drifts"] >= 1
    assert octo.get("/api/overview").json()["prs_checked"] >= 1
    assert octo.get("/api/issues").json()
    assert octo.get("/api/reports").json()


def test_another_maintainer_cannot_see_it(two_users):
    octo = client_for("octo-cookie")
    issue_id = octo.get("/api/issues").json()[0]["id"]
    report_id = octo.get("/api/reports").json()[0]["id"]

    mona = client_for("mona-cookie")
    assert [r["id"] for r in mona.get("/api/repositories").json()] == ["mona/other"]
    assert mona.get("/api/issues").json() == []
    assert mona.get("/api/reports").json() == []
    assert mona.get("/api/autofix/proposals").json() == []
    assert mona.get("/api/overview").json()["total_active_drifts"] == 0
    assert mona.get(f"/api/issues/{issue_id}").status_code == 404
    assert mona.get(f"/api/reports/{report_id}").status_code == 404
    assert mona.post("/api/scan/live", json={"repo_id": "octo/app"}).status_code == 404


def test_hosted_fixes_point_to_github_instead_of_a_server_copy(two_users):
    octo = client_for("octo-cookie")
    issue_id = octo.get("/api/issues").json()[0]["id"]
    assert octo.post(f"/api/issues/{issue_id}/fix").status_code == 400


def test_sync_status_and_trigger(two_users):
    octo = client_for("octo-cookie")
    assert octo.get("/api/sync/status").json()["state"] == "idle"
    assert octo.post("/api/sync").json() == {"started": True}
    assert github_auth.sync_wanted.is_set()
    github_auth.sync_wanted.clear()


def test_the_same_commit_always_gives_the_same_answer(github):
    first = sync.scan_repository("octo/app", "tok", pr_number=7)
    second = sync.scan_repository("octo/app", "tok", pr_number=7)
    assert second[0] == first[0]  # The saved report, not a new scan.
    assert second[3].total_drifts == first[3].total_drifts == 1
    assert [f.outdated_excerpt for f in second[3].drifts()] == ["Use --timeout to stop slow jobs."]
    assert second[3].generate_markdown_report() == first[3].generate_markdown_report()


def test_refs_are_saved_as_exact_commits(github):
    _, base, head, _ = sync.scan_repository("octo/app", "tok", pr_number=7)
    assert head == github["head"]
    assert len(base) == 40


def paraphrase_repo(github):
    work = github["work"]
    git(work, "switch", "-q", "main")
    (work / "cli.py").write_text('parser.add_argument("--timeout")\nTTL = 300\n')
    (work / "README.md").write_text("Results stay available for 300 seconds.\n")
    git(work, "commit", "-qam", "base")
    git(work, "switch", "-qc", "ttl")
    (work / "cli.py").write_text('parser.add_argument("--timeout")\nTTL = 900\n')
    git(work, "commit", "-qam", "ttl")
    head = git(work, "rev-parse", "HEAD")
    git(work, "push", "-q", "--force", str(github["bare"]), "main", f"{head}:refs/pull/8/head")
    return head


def test_a_result_waiting_for_the_model_is_finished_when_it_returns(github, monkeypatch):
    paraphrase_repo(github)
    first = sync.scan_repository("octo/app", "tok", pr_number=8)
    assert first[3].possible_drifts == 1 and first[3].complete is False

    # Still no model: the same answer.
    assert sync.scan_repository("octo/app", "tok", pr_number=8)[0] == first[0]

    class YesQwen(QwenProvider):
        def _describes_setting(self, pair, sentence):
            return True

    monkeypatch.setattr(sync, "get_ai_provider", lambda: YesQwen())
    monkeypatch.setattr("backend.app.analyzer.pipeline.get_ai_provider", lambda: YesQwen())
    upgraded = sync.scan_repository("octo/app", "tok", pr_number=8)
    assert upgraded[3].confirmed_drifts == 1 and upgraded[3].complete is True
    assert [i["verdict"] for i in issues_for("octo/app")] == ["CONFIRMED_DRIFT"]

    # A finished result stays finished, even if the model goes away again.
    monkeypatch.setattr(sync, "get_ai_provider", lambda: HeuristicAIProvider())
    monkeypatch.setattr("backend.app.analyzer.pipeline.get_ai_provider", lambda: HeuristicAIProvider())
    assert sync.scan_repository("octo/app", "tok", pr_number=8)[3].confirmed_drifts == 1


def test_repo_score_follows_open_issues(github):
    sync.scan_repository("octo/app", "tok", pr_number=7)
    conn = db.get_db_connection()
    score = lambda: conn.execute("SELECT health_score FROM repositories WHERE id = 'octo/app'").fetchone()[0]
    assert score() == 82.0
    conn.close()
    db.mark_issue_fixed(issues_for("octo/app")[0]["id"])
    conn = db.get_db_connection()
    assert score() == 100.0
    conn.close()
