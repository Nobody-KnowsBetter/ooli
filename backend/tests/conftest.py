"""Runs tests against a throwaway database, without needing a model."""
import os
import tempfile
from pathlib import Path

os.environ["DOCGUARD_DB_PATH"] = str(Path(tempfile.mkdtemp()) / "test.db")
os.environ["DOCGUARD_AI_PROVIDER"] = "heuristic"
os.environ["GITHUB_CLIENT_ID"] = ""
os.environ["GITHUB_CLIENT_SECRET"] = ""
os.environ.setdefault("APP_URL", "http://localhost:3000")
