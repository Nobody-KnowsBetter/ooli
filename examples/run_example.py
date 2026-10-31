"""Runs DocGuard on examples/flag_rename/input and writes the report it produces to output.md."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.ai.intelligence import model_status  # noqa: E402
from backend.app.analyzer.pipeline import run_analysis  # noqa: E402

INPUT = ROOT / "examples" / "flag_rename" / "input"


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=example", "-c", "user.email=example@example.com", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


with tempfile.TemporaryDirectory() as tmp:
    repo = Path(tmp)
    git(repo, "init", "-q")
    shutil.copy(INPUT / "README.md", repo / "README.md")
    shutil.copy(INPUT / "cli_before.py", repo / "cli.py")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "before")
    shutil.copy(INPUT / "cli_after.py", repo / "cli.py")
    git(repo, "commit", "-qam", "after")
    report = run_analysis(repo, "HEAD~1", "HEAD").generate_markdown_report()

output = ROOT / "examples" / "flag_rename" / "output.md"
output.write_text(f"<!-- Produced by examples/run_example.py with {model_status()['model']}. -->\n{report}")
print(report)
