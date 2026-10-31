"""DocGuard 10-Scenario Test Suite.

Validates precision, recall, and epistemic modesty across all core requirements.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from backend.app.ai.intelligence import HeuristicAIProvider
from backend.app.analyzer.ast_analyzer import compare_python_ast
from backend.app.analyzer.doc_chunker import chunk_markdown_file
from backend.app.analyzer.doc_mapper import map_changes_to_docs
from backend.app.analyzer.models import ChangeType, Finding, Verdict


@pytest.fixture
def provider() -> HeuristicAIProvider:
    return HeuristicAIProvider()


def analyze_code_and_doc(
    old_py: str,
    new_py: str,
    doc_content: str,
    py_filename: str = "src/service.py",
    doc_filename: str = "docs/guide.md",
) -> list[Finding]:
    """Helper to run AST diffing, doc chunking, candidate mapping, and AI evaluation."""
    changes = compare_python_ast(py_filename, old_py, new_py)
    sections = chunk_markdown_file(doc_filename, doc_content)
    candidates = map_changes_to_docs(changes, sections)
    provider = HeuristicAIProvider()
    return [provider.evaluate(c) for c in candidates]


# Scenario 1: A constant changes and documentation is not updated
def test_scenario_1_constant_changed_doc_not_updated():
    old_py = "TIMEOUT_SECONDS = 30\n"
    new_py = "TIMEOUT_SECONDS = 90\n"
    doc = "# Configuration\nThe request timeout is 30 seconds."

    findings = analyze_code_and_doc(old_py, new_py, doc)
    assert len(findings) == 1
    f = findings[0]
    assert f.verdict == Verdict.CONFIRMED_DRIFT
    assert f.confidence >= 0.85
    assert "TIMEOUT_SECONDS" in f.changed_symbol
    assert "90" in f.suggested_fix
    assert "30" in f.outdated_excerpt


# Scenario 2: A constant changes and documentation is updated correctly
def test_scenario_2_constant_changed_doc_updated_correctly():
    old_py = "TIMEOUT_SECONDS = 30\n"
    new_py = "TIMEOUT_SECONDS = 90\n"
    # Doc in the same PR already reflects 90!
    doc = "# Configuration\nThe request timeout is 90 seconds."

    findings = analyze_code_and_doc(old_py, new_py, doc)
    # Either no candidates or evaluated as NO_DRIFT_DETECTED
    drifts = [f for f in findings if f.verdict == Verdict.CONFIRMED_DRIFT]
    assert len(drifts) == 0


# Scenario 3: A function is renamed but documentation still uses the old name
def test_scenario_3_function_renamed_doc_uses_old_name():
    old_py = "def fetch_user_data(user_id: int):\n    return {}\n"
    new_py = "def get_user_profile(user_id: int):\n    return {}\n"
    doc = "## User API\nCall `fetch_user_data(user_id)` to retrieve user details."

    findings = analyze_code_and_doc(old_py, new_py, doc)
    drift_findings = [f for f in findings if f.verdict == Verdict.CONFIRMED_DRIFT]
    assert len(drift_findings) >= 1
    f = drift_findings[0]
    assert f.change_type == ChangeType.FUNCTION_RENAMED
    assert "fetch_user_data" in f.outdated_excerpt
    assert "get_user_profile" in f.suggested_fix


# Scenario 4: A function parameter is removed but documentation still mentions it
def test_scenario_4_param_removed_doc_still_mentions_it():
    old_py = "def connect_db(host: str, port: int, use_ssl: bool = False):\n    pass\n"
    new_py = "def connect_db(host: str, port: int):\n    pass\n"
    doc = "## Database\n`connect_db`: options include `host`, `port`, and `use_ssl`."

    findings = analyze_code_and_doc(old_py, new_py, doc)
    drift_findings = [f for f in findings if f.verdict == Verdict.CONFIRMED_DRIFT]
    assert len(drift_findings) >= 1
    f = drift_findings[0]
    assert f.change_type == ChangeType.PARAMETER_REMOVED
    assert "use_ssl" in f.explanation or "use_ssl" in f.outdated_excerpt


# Scenario 5: An API endpoint changes
def test_scenario_5_api_endpoint_changes():
    old_py = "@app.get('/api/v1/users')\ndef list_users():\n    return []\n"
    new_py = "@app.get('/api/v2/users')\ndef list_users():\n    return []\n"
    doc = "## API Reference\nSend GET request to `/api/v1/users` to list all members."

    findings = analyze_code_and_doc(old_py, new_py, doc)
    drift_findings = [f for f in findings if f.verdict == Verdict.CONFIRMED_DRIFT]
    assert len(drift_findings) >= 1
    f = drift_findings[0]
    assert f.change_type == ChangeType.API_ENDPOINT_CHANGED
    assert "/api/v1/users" in f.outdated_excerpt
    assert "/api/v2/users" in f.suggested_fix


# Scenario 6: A configuration default changes
def test_scenario_6_config_default_changes():
    old_py = "MAX_CONNECTIONS = 10\n"
    new_py = "MAX_CONNECTIONS = 50\n"
    doc = "### Pool Settings\nDefault `MAX_CONNECTIONS` is 10 connections."

    findings = analyze_code_and_doc(old_py, new_py, doc)
    drift_findings = [f for f in findings if f.verdict == Verdict.CONFIRMED_DRIFT]
    assert len(drift_findings) == 1
    assert "50" in drift_findings[0].suggested_fix


# Scenario 7: Documentation is completely unrelated to the changed code
def test_scenario_7_unrelated_documentation():
    old_py = "def calculate_tax(amount: float):\n    return amount * 0.1\n"
    new_py = "def calculate_tax(amount: float):\n    return amount * 0.15\n"
    doc = "# MIT License\nPermission is hereby granted free of charge..."

    findings = analyze_code_and_doc(old_py, new_py, doc)
    drifts = [f for f in findings if f.verdict == Verdict.CONFIRMED_DRIFT]
    assert len(drifts) == 0


# Scenario 8: A PR changes internal code without requiring documentation updates
def test_scenario_8_internal_refactor_no_doc_drift():
    old_py = "def process():\n    res = []\n    for i in range(5):\n        res.append(i)\n    return res\n"
    new_py = "def process():\n    return [i for i in range(5)]\n"
    doc = "## Process\nCall `process()` to retrieve the list of indices."

    findings = analyze_code_and_doc(old_py, new_py, doc)
    drifts = [f for f in findings if f.verdict == Verdict.CONFIRMED_DRIFT]
    assert len(drifts) == 0


# Scenario 9: Multiple documentation files refer to the same code
def test_scenario_9_multiple_docs_referencing_same_code():
    old_py = "PORT = 8080\n"
    new_py = "PORT = 9000\n"
    doc1 = "# Getting Started\nThe server starts on port 8080 by default."
    doc2 = "# Deployment Guide\nExpose port 8080 in your Docker container."

    changes = compare_python_ast("src/server.py", old_py, new_py)
    sections = chunk_markdown_file("docs/start.md", doc1) + chunk_markdown_file("docs/deploy.md", doc2)
    candidates = map_changes_to_docs(changes, sections)
    provider = HeuristicAIProvider()
    findings = [provider.evaluate(c) for c in candidates]

    drift_files = {f.doc_file for f in findings if f.verdict == Verdict.CONFIRMED_DRIFT}
    assert "docs/start.md" in drift_files
    assert "docs/deploy.md" in drift_files


# Scenario 10: Ambiguous or insufficient evidence returns modest confidence / uncertain
def test_scenario_10_ambiguous_evidence():
    old_py = "class SessionManager:\n    pass\n"
    new_py = "class SessionManager:\n    def ping(self): pass\n"
    # General doc mentioning sessions but no concrete interface contradicted
    doc = "# Architecture\nOur backend maintains user sessions for stateful requests."

    findings = analyze_code_and_doc(old_py, new_py, doc)
    for f in findings:
        assert f.verdict != Verdict.CONFIRMED_DRIFT
        if f.verdict == Verdict.POSSIBLE_DRIFT:
            assert f.confidence <= 0.65

