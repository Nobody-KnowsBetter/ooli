"""Runs tests against a throwaway database, without needing a model."""
import os
import tempfile
from pathlib import Path

os.environ["DOCGUARD_DB_PATH"] = str(Path(tempfile.mkdtemp()) / "test.db")
os.environ["DOCGUARD_AI_PROVIDER"] = "heuristic"
