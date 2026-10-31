"""End-to-end checks on real git history: what must be caught, and what must stay quiet."""
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from backend.app.ai import intelligence
from backend.app.analyzer.models import CandidatePair, ChangeType, CodeChange, DocSection, Verdict
from backend.app.analyzer.pipeline import run_analysis
from backend.app.autofix.patcher import generate_fix_preview
from backend.app.analyzer.models import Finding
from backend.app.repos import RepoError, merge_base_of_pr, parse_repo_name, resolve_refs


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def scan(tmp_path: Path, old: str, new: str, doc: str, doc_name: str = "README.md", new_doc: str | None = None):
    git(tmp_path, "init", "-q")
    (tmp_path / "cli.py").write_text(old)
    (tmp_path / doc_name).write_text(doc)
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "before")
    (tmp_path / "cli.py").write_text(new)
    if new_doc is not None:
        (tmp_path / doc_name).write_text(new_doc)
    git(tmp_path, "commit", "-qam", "after")
    return [f for f in run_analysis(tmp_path, "HEAD~1", "HEAD").findings if f.verdict != Verdict.NO_DRIFT_DETECTED]


def test_flag_rename_from_the_hackathon_slide(tmp_path):
    findings = scan(
        tmp_path,
        'parser.add_argument("--timeout")\n',
        'parser.add_argument("--deadline")\n',
        "# Usage\n\nUse --timeout to stop slow jobs.\n",
    )
    assert len(findings) == 1
    assert findings[0].verdict == Verdict.CONFIRMED_DRIFT
    assert findings[0].change_type == ChangeType.FLAG_RENAMED
    assert findings[0].doc_start_line == 3
    assert findings[0].suggested_fix == "Use --deadline to stop slow jobs."


def test_flag_default_change(tmp_path):
    findings = scan(
        tmp_path,
        'parser.add_argument("--retries", default=3)\n',
        'parser.add_argument("--retries", default=5)\n',
        "`--retries` defaults to 3.\n",
    )
    assert [f.verdict for f in findings] == [Verdict.CONFIRMED_DRIFT]
    assert "5" in findings[0].suggested_fix


def test_click_option_rename(tmp_path):
    findings = scan(
        tmp_path,
        '@click.option("--name")\ndef run(name): pass\n',
        '@click.option("--label")\ndef run(name): pass\n',
        "Pass --name to set it.\n",
    )
    assert findings[0].suggested_fix == "Pass --label to set it."


def test_paraphrase_without_the_name_is_only_possible_drift(tmp_path):
    findings = scan(tmp_path, "TIMEOUT = 30\n", "TIMEOUT = 60\n", "Requests give up after 30 seconds.\n")
    assert [f.verdict for f in findings] == [Verdict.POSSIBLE_DRIFT]


@pytest.mark.parametrize(
    "old, new, doc",
    [
        # Mentioned, but nothing it says became wrong.
        ("MAX_RETRIES = 3\n", "MAX_RETRIES = 4\n", "MAX_RETRIES is covered in chapter 12.\n"),
        # A sentence about the past.
        ("TIMEOUT = 30\n", "TIMEOUT = 60\n", "Before 2.0, TIMEOUT was 30.\n"),
        # Only looks like the old value.
        ("TIMEOUT = 30\n", "TIMEOUT = 60\n", "TIMEOUT can go up to 300.\n"),
        # A single digit proves nothing.
        ("LIMIT = 3\n", "LIMIT = 4\n", "There are 3 steps.\n"),
        # Private names aren't documented for users.
        ("_TIMEOUT = 30\n", "_TIMEOUT = 60\n", "The _TIMEOUT is 30.\n"),
    ],
)
def test_stays_quiet(tmp_path, old, new, doc):
    assert scan(tmp_path, old, new, doc) == []


def test_changelog_may_mention_old_values(tmp_path):
    assert scan(tmp_path, "TIMEOUT = 30\n", "TIMEOUT = 60\n", "TIMEOUT is 30.\n", doc_name="CHANGELOG.md") == []


def test_doc_fixed_in_the_same_change_is_not_flagged(tmp_path):
    findings = scan(
        tmp_path,
        'parser.add_argument("--timeout")\n',
        'parser.add_argument("--deadline")\n',
        "Use --timeout.\n",
        new_doc="Use --deadline.\n",
    )
    assert findings == []


def test_docs_are_read_at_the_commit_not_the_working_folder(tmp_path):
    scan(tmp_path, "TIMEOUT = 30\n", "TIMEOUT = 60\n", "TIMEOUT is 30.\n")
    (tmp_path / "README.md").write_text("TIMEOUT is 60.\n")  # An uncommitted edit.
    findings = run_analysis(tmp_path, "HEAD~1", "HEAD").findings
    assert [f.verdict for f in findings] == [Verdict.CONFIRMED_DRIFT]


def pair() -> CandidatePair:
    change = CodeChange("cli.py", ChangeType.CONSTANT_CHANGED, "TIMEOUT", "30", "60")
    return CandidatePair(change, DocSection("README.md", "Usage", "# Usage\nRequests give up after 30 seconds.", 1, 2))


def fake_model(monkeypatch, answer):
    def post(url, json, timeout):
        assert url.endswith("/api/chat")
        assert json["model"] == intelligence.DEFAULT_MODEL
        assert "Requests give up after 30 seconds." in json["messages"][1]["content"]
        if isinstance(answer, Exception):
            raise answer
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json={"message": {"content": answer}})

    monkeypatch.setattr(intelligence.httpx, "post", post)


def test_model_confirms_a_paraphrase_and_the_fix_comes_from_rules(monkeypatch):
    fake_model(monkeypatch, json.dumps({"describes_setting": True}))
    finding = intelligence.QwenProvider().evaluate(pair())
    assert finding.verdict == Verdict.CONFIRMED_DRIFT
    assert finding.doc_start_line == 2
    assert finding.suggested_fix == "Requests give up after 60 seconds."
    assert finding.engine == intelligence.DEFAULT_MODEL


def test_model_dismisses_a_coincidence(monkeypatch):
    fake_model(monkeypatch, json.dumps({"describes_setting": False}))
    finding = intelligence.QwenProvider().evaluate(pair())
    assert finding.verdict == Verdict.NO_DRIFT_DETECTED
    assert finding.engine == intelligence.DEFAULT_MODEL


def test_model_checks_every_sentence_holding_the_old_value(monkeypatch):
    asked = []

    def post(url, json, timeout):
        sentence = json["messages"][1]["content"].rsplit("Sentence: ", 1)[1].split("\n")[0]
        asked.append(sentence)
        request = httpx.Request("POST", url)
        answer = {"describes_setting": "give up" in sentence}
        return httpx.Response(200, request=request, json={"message": {"content": _json.dumps(answer)}})

    _json = json
    monkeypatch.setattr(intelligence.httpx, "post", post)
    change = CodeChange("cli.py", ChangeType.CONSTANT_CHANGED, "TIMEOUT", "30", "60")
    section = DocSection("README.md", "Usage", "This guide has 30 pages.\nRequests give up after 30 seconds.", 1, 2)
    finding = intelligence.QwenProvider().evaluate(CandidatePair(change, section))
    assert asked == ["This guide has 30 pages.", "Requests give up after 30 seconds."]
    assert finding.verdict == Verdict.CONFIRMED_DRIFT
    assert finding.doc_start_line == 2
    assert finding.suggested_fix == "Requests give up after 60 seconds."


def test_rules_decide_exact_matches_without_the_model(monkeypatch):
    def post(*args, **kwargs):
        raise AssertionError("The model should not be called")

    monkeypatch.setattr(intelligence.httpx, "post", post)
    change = CodeChange("cli.py", ChangeType.CONSTANT_CHANGED, "TIMEOUT", "30", "60")
    section = DocSection("README.md", "Usage", "The TIMEOUT is 30.", 1, 1)
    finding = intelligence.QwenProvider().evaluate(CandidatePair(change, section))
    assert finding.verdict == Verdict.CONFIRMED_DRIFT
    assert finding.engine == "heuristic"


@pytest.mark.parametrize(
    "failure",
    [httpx.ConnectError("down"), "not json", json.dumps({"something": "else"}), json.dumps([1])],
)
def test_keeps_it_as_possible_drift_when_the_model_fails(monkeypatch, failure):
    fake_model(monkeypatch, failure)
    finding = intelligence.QwenProvider().evaluate(pair())
    assert finding.engine == "heuristic"
    assert finding.verdict == Verdict.POSSIBLE_DRIFT


@pytest.mark.parametrize("path", ["../secret.md", "cli.py"])
def test_fixes_cannot_touch_other_files(tmp_path, path):
    (tmp_path / "repo").mkdir()
    (tmp_path / "secret.md").write_text("old")
    (tmp_path / "repo" / "cli.py").write_text("old")
    finding = Finding(Verdict.CONFIRMED_DRIFT, 1.0, "", "", path, 1, 1, "old", "", "new")
    assert not generate_fix_preview(tmp_path / "repo", finding).is_applicable


def test_repository_names():
    assert parse_repo_name("https://github.com/psf/requests.git") == "psf/requests"
    assert parse_repo_name("psf/requests") == "psf/requests"
    for bad in ["../../etc", "https://evil.example/a/b", "a/b/c", "--upload-pack=x/y"]:
        with pytest.raises(RepoError):
            parse_repo_name(bad)


def test_refs_that_git_would_read_as_options_are_rejected(tmp_path):
    with pytest.raises(RepoError):
        resolve_refs(tmp_path, "a/b", "--output=/tmp/x", "HEAD", None)


def rev(repo: Path, ref: str) -> str:
    return subprocess.run(["git", "rev-parse", ref], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


def commit(repo: Path, name: str, *extra: str) -> None:
    (repo / name).write_text(name)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", name, *extra)


def test_finds_the_branch_point_of_open_and_merged_prs(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    commit(tmp_path, "start.txt")
    branch_point = rev(tmp_path, "HEAD")
    git(tmp_path, "switch", "-qc", "feature")
    commit(tmp_path, "feature.txt")
    head = rev(tmp_path, "HEAD")
    git(tmp_path, "switch", "-q", "main")
    commit(tmp_path, "other.txt")

    assert merge_base_of_pr(tmp_path, "main", head, 1) == branch_point  # Still open

    git(tmp_path, "merge", "-q", "--no-ff", "-m", "merge", "feature")
    assert merge_base_of_pr(tmp_path, "main", head, 1) == branch_point  # Merged, not an empty diff


def test_the_cli_works_on_a_fresh_machine_without_falling_back(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    scan(repo, 'p.add_argument("--timeout")\n', 'p.add_argument("--deadline")\n', "Use --timeout.\n")
    project = Path(__file__).resolve().parents[2]
    code = (
        "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1])\n"
        "from backend.app.analyzer.pipeline import run_analysis\n"
        "print(run_analysis(Path(sys.argv[2]), 'HEAD~1', 'HEAD').confirmed_drifts)"
    )
    env = {
        "PATH": os.environ["PATH"],
        "DOCGUARD_DB_PATH": str(tmp_path / "fresh.db"),
        "OLLAMA_URL": "http://127.0.0.1:1",  # Nothing listens here, like CI without a model.
    }
    result = subprocess.run(
        [sys.executable, "-c", code, str(project), str(repo)], capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1"
