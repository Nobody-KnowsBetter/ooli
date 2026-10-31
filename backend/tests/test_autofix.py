"""Tests for Auto-Fix patcher and unified diff generator."""
from pathlib import Path
import tempfile

from backend.app.analyzer.models import ChangeType, Finding, Verdict
from backend.app.autofix.patcher import apply_fix, generate_fix_preview


def test_autofix_generate_and_apply():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        doc_path = root / "docs" / "test.md"
        doc_path.parent.mkdir(parents=True)
        doc_path.write_text("The default timeout is 30 seconds.\n", encoding="utf-8")

        finding = Finding(
            verdict=Verdict.CONFIRMED_DRIFT,
            confidence=0.98,
            source_file="src/config.py",
            changed_symbol="TIMEOUT_SECONDS",
            doc_file="docs/test.md",
            doc_start_line=1,
            doc_end_line=1,
            outdated_excerpt="The default timeout is 30 seconds.",
            explanation="Timeout changed from 30 to 60.",
            suggested_fix="The default timeout is 60 seconds.",
            change_type=ChangeType.CONSTANT_CHANGED,
            code_diff="- TIMEOUT_SECONDS = 30\n+ TIMEOUT_SECONDS = 60",
        )

        preview = generate_fix_preview(root, finding)
        assert preview.is_applicable is True
        assert "-The default timeout is 30 seconds." in preview.diff
        assert "+The default timeout is 60 seconds." in preview.diff

        success = apply_fix(root, preview)
        assert success is True
        assert doc_path.read_text(encoding="utf-8") == "The default timeout is 60 seconds.\n"

