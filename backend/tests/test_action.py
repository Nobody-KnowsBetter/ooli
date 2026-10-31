"""Runs the command line the way the GitHub Action does, on a real git repository."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[2]
CLI = PROJECT / "backend" / "src" / "docguard.py"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def make_repo(path: Path, old: str, new: str, doc: str) -> tuple[str, str]:
    git(path, "init", "-q")
    (path / "cli.py").write_text(old)
    (path / "README.md").write_text(doc)
    git(path, "add", ".")
    git(path, "commit", "-qm", "before")
    base = git(path, "rev-parse", "HEAD")
    (path / "cli.py").write_text(new)
    git(path, "commit", "-qam", "after")
    return base, git(path, "rev-parse", "HEAD")


def run_cli(repo: Path, tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    # Runs from the user's repository with only what CI has, like the Action.
    env = {
        "PATH": os.environ["PATH"],
        "GITHUB_ACTIONS": "true",
        "GITHUB_OUTPUT": str(tmp_path / "output.txt"),
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": "octo/app",
        "DOCGUARD_AI_PROVIDER": "heuristic",
    }
    return subprocess.run(
        [sys.executable, str(CLI), "--report", str(tmp_path / "report.md"), *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    return path


FLAG_OLD = 'parser.add_argument("--timeout")\n'
FLAG_NEW = 'parser.add_argument("--deadline")\n'


def test_reports_the_sentence_and_the_code_change_with_links(repo, tmp_path):
    base, head = make_repo(repo, FLAG_OLD, FLAG_NEW, "# Usage\n\nUse --timeout to stop slow jobs.\n")
    result = run_cli(repo, tmp_path, "--base", base, "--head", head)
    assert result.returncode == 0, result.stderr

    report = (tmp_path / "report.md").read_text()
    assert "> Use --timeout to stop slow jobs." in report
    assert "> Use --deadline to stop slow jobs." in report
    assert f"https://github.com/octo/app/blob/{head}/README.md#L3" in report
    assert f"https://github.com/octo/app/blob/{head}/cli.py#L1" in report

    assert "::warning file=README.md,line=3,title=DocGuard::" in result.stdout
    assert "drift-count=1\n" in (tmp_path / "output.txt").read_text()


def test_clean_change_reports_no_drift(repo, tmp_path):
    base, head = make_repo(repo, FLAG_OLD, FLAG_NEW, "Nothing relevant here.\n")
    result = run_cli(repo, tmp_path, "--base", base, "--head", head)
    assert result.returncode == 0
    assert "No drift found" in (tmp_path / "report.md").read_text()
    assert "drift-count=0\n" in (tmp_path / "output.txt").read_text()


def test_paraphrase_reports_possible_so_the_action_knows_to_start_the_model(repo, tmp_path):
    base, head = make_repo(repo, "TIMEOUT = 30\n", "TIMEOUT = 60\n", "Requests give up after 30 seconds.\n")
    result = run_cli(repo, tmp_path, "--base", base, "--head", head)
    assert "possible-count=1\n" in (tmp_path / "output.txt").read_text()
    assert "::notice file=README.md,line=1" in result.stdout


def test_fail_on_drift_only_fails_on_confirmed_drift(repo, tmp_path):
    base, head = make_repo(repo, FLAG_OLD, FLAG_NEW, "Use --timeout.\n")
    assert run_cli(repo, tmp_path, "--base", base, "--head", head, "--fail-on-drift").returncode == 1


def test_a_broken_check_never_breaks_the_pull_request(repo, tmp_path):
    make_repo(repo, FLAG_OLD, FLAG_NEW, "Use --timeout.\n")
    result = run_cli(repo, tmp_path, "--base", "HEAD~1", "--head", "does-not-exist")
    assert result.returncode == 0
    assert "::warning title=DocGuard::DocGuard could not check this change" in result.stdout


def test_a_shallow_clone_warns_instead_of_claiming_no_drift(repo, tmp_path):
    base, head = make_repo(repo, FLAG_OLD, FLAG_NEW, "Use --timeout.\n")
    shallow = tmp_path / "shallow"
    git(tmp_path, "clone", "-q", "--depth", "1", f"file://{repo}", str(shallow))
    result = run_cli(shallow, tmp_path, "--base", base, "--head", head)
    assert result.returncode == 0
    assert "fetch-depth: 0" in result.stdout
    assert "No drift" not in result.stdout


def test_docs_cannot_inject_workflow_commands(repo, tmp_path):
    malicious = 'parser.add_argument("--a\\n::error::hacked")\n'
    base, head = make_repo(repo, malicious, 'parser.add_argument("--b")\n', "Use --a\n")
    result = run_cli(repo, tmp_path, "--base", base, "--head", head)
    assert "\n::error::hacked" not in result.stdout.split("## DocGuard report")[0]
    for line in result.stdout.splitlines():
        if line.startswith("::warning"):
            assert "%0A" in line or "::error" not in line


def test_works_when_the_user_repository_has_python_files_named_like_ours(repo, tmp_path):
    (repo / "backend").mkdir()
    (repo / "backend" / "__init__.py").write_text("raise RuntimeError('user code must not be imported')\n")
    base, head = make_repo(repo, FLAG_OLD, FLAG_NEW, "Use --timeout.\n")
    result = run_cli(repo, tmp_path, "--base", base, "--head", head)
    assert result.returncode == 0, result.stderr
    assert "drift-count=1\n" in (tmp_path / "output.txt").read_text()


def test_the_action_file_is_valid():
    yaml = pytest.importorskip("yaml")
    action = yaml.safe_load((PROJECT / "action.yml").read_text())
    assert action["runs"]["using"] == "composite"
    ids = [step.get("id") for step in action["runs"]["steps"]]
    assert {"rules", "model", "qwen", "final"} <= set(ids)
