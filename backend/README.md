# 🛡️ DocGuard — AI-Powered Documentation Intelligence Platform

> **Prevent documentation rot before code merges.** DocGuard analyzes code changes, inspects corresponding documentation, detects semantic documentation drift with grounded evidence, and generates one-click automated fixes.

[![DocGuard CI](https://github.com/krishgarg-code/JavaBasicPrograms1/actions/workflows/docguard.yml/badge.svg)](https://github.com/krishgarg-code/JavaBasicPrograms1/actions/workflows/docguard.yml)
[![Tests](https://img.shields.io/badge/tests-17%20passed-emerald)](tests/)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.14-blue)](backend/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## 🚀 The Problem

Developers constantly modify code without updating documentation:
```python
# In src/config.py
TIMEOUT_SECONDS = 13456  # Changed from 30
```
While documentation quietly rots:
```markdown
# In docs/configuration.md
The request timeout is 30 seconds.
```

Traditional CI/CD linters test code execution and syntax, but fail to detect when ordinary English prose, parameter tables, tutorials, or API guides contradict code.

DocGuard solves this by combining **deterministic Python AST analysis** with **grounded AI reasoning** to verify documentation accuracy on every commit and Pull Request.

---

## ⚡ Architecture Pipeline

DocGuard avoids generic LLM hallucination by employing a structured analysis funnel:

```
Pull Request Event / Commit Diff
               │
               ▼
┌───────────────────────────────────────────────┐
│        Deterministic Extraction Layer         │
│  • Git Unified Diff & Hunk Parser             │
│  • Python AST Analyzer (Funcs, API, Config)   │
│  • Markdown Chunker & Section Indexer         │
└───────────────────────┬───────────────────────┘
                        │ Candidate Code-Doc Pairs
                        ▼
┌───────────────────────────────────────────────┐
│       AI Semantic Intelligence Engine         │
│  • Multi-Provider Support (Gemini/OpenAI/Heur)│
│  • Evidence Verification & Grounding          │
│  • Strict JSON Schema & Confidence Scoring    │
└───────────────────────┬───────────────────────┘
                        │
         ┌──────────────┴──────────────┐
         ▼                             ▼
┌──────────────────┐          ┌──────────────────┐
│ GitHub PR Review │          │  Auto-Fix Engine │
│  & Action Report │          │ & Web Dashboard  │
└──────────────────┘          └──────────────────┘
```

---

## ✨ Features

- **AST Structural Intelligence**: Detects modified constants, changed function signatures, removed parameters, API route changes (`@app.get(...)`), and configuration defaults.
- **Section-Aware Markdown Chunking**: Parses markdown headers, tables, and code blocks with exact line numbers.
- **Evidence-Grounded Verdicts**:
  - `CONFIRMED DRIFT`: Strong evidence of contradictory documentation.
  - `POSSIBLE DRIFT`: Ambiguous changes with epistemically modest confidence.
  - `NO DRIFT DETECTED`: Documentation already updated or code refactor preserves external contracts.
- **Auto-Fix Engine**: Computes unified diffs and replacement blocks for outdated prose, ready for one-click human approval.
- **Interactive Web Dashboard**: Linear/Vercel-inspired dark-mode UI with side-by-side diff comparisons and repository health tracking.
- **Zero-Breakage GitHub Action**: Drop-in compatibility with GitHub Actions using standard library fallback.

---

## 🛠️ Quickstart

### 1. Run the CLI Locally
```bash
# Clone the repository
git clone https://github.com/krishgarg-code/JavaBasicPrograms1.git
cd JavaBasicPrograms1

# Run analysis between two git references
python3 src/docguard.py --base HEAD~1 --head HEAD
```

To automatically apply suggested fixes:
```bash
python3 src/docguard.py --base HEAD~1 --head HEAD --autofix
```

### 2. Run the Web Dashboard & API

**Terminal 1 — FastAPI Backend Service:**
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Start backend on port 8000
uvicorn backend.app.main:app --reload --port 8000
```
API & Swagger docs will be live at **[http://localhost:8000/docs](http://localhost:8000/docs)**.

**Terminal 2 — Next.js React Dashboard:**
```bash
# Navigate to frontend and install dependencies
cd frontend
npm install

# Start development server on port 3000
npm run dev
```
Open **[http://localhost:3000](http://localhost:3000)** in your browser to access the production-grade DocGuard Web Dashboard.

---

### 3. Run the Test Suite
```bash
source .venv/bin/activate
PYTHONPATH=. pytest tests/ -v
```
All 21 test cases (including the 10 core drift scenarios and API tests) will execute and validate.

---

## 🧪 10 Core Test Scenarios Covered

| # | Test Scenario | Expected Verdict | Verified |
|---|---|---|:---:|
| 1 | Constant changed; Doc not updated | `CONFIRMED_DRIFT` | ✅ |
| 2 | Constant changed; Doc updated in same PR | `NO_DRIFT_DETECTED` | ✅ |
| 3 | Function renamed; Doc references old name | `CONFIRMED_DRIFT` | ✅ |
| 4 | Parameter removed; Doc lists old parameter | `CONFIRMED_DRIFT` | ✅ |
| 5 | API endpoint route changed | `CONFIRMED_DRIFT` | ✅ |
| 6 | Configuration default changed | `CONFIRMED_DRIFT` | ✅ |
| 7 | Unrelated doc (e.g. License/Contributing) | `NO_DRIFT_DETECTED` | ✅ |
| 8 | Refactoring without interface change | `NO_DRIFT_DETECTED` | ✅ |
| 9 | Multiple docs referencing same symbol | `CONFIRMED_DRIFT` | ✅ |
| 10 | Ambiguous/Insufficient evidence | `POSSIBLE_DRIFT` / `NO_DRIFT_DETECTED` | ✅ |

---

## 📁 Repository Structure

```text
JavaBasicPrograms1/
├── backend/
│   ├── app/
│   │   ├── analyzer/
│   │   │   ├── ast_analyzer.py      # Python AST parsing & structural comparison
│   │   │   ├── diff_parser.py       # Unified git diff parser
│   │   │   ├── doc_chunker.py       # Markdown sectioning & symbol indexing
│   │   │   ├── doc_mapper.py        # Code-to-doc candidate matcher
│   │   │   ├── models.py            # Pydantic & Dataclass domain models
│   │   │   └── pipeline.py          # Analysis pipeline coordinator
│   │   ├── ai/
│   │   │   ├── intelligence.py      # Grounded AI & heuristic intelligence engine
│   │   │   └── prompts.py           # Structured prompt schemas
│   │   ├── autofix/
│   │   │   └── patcher.py           # Unified diff generation & patch applier
│   │   ├── database/
│   │   │   └── db.py                # SQLite persistence layer
│   │   └── main.py                  # FastAPI server & GitHub webhook receiver
│   └── requirements.txt
├── frontend/
│   └── public/
│       └── index.html               # Linear/Vercel inspired dark-mode dashboard
├── src/
│   ├── config.py                    # Demo configuration
│   └── docguard.py                  # Standalone CLI & GitHub Actions runner
├── docs/
│   └── configuration.md             # Documentation demo
├── tests/
│   ├── test_api.py                  # FastAPI endpoint test suite
│   ├── test_autofix.py              # Auto-Fix unit tests
│   └── test_scenarios.py            # 10 core drift scenario tests
├── .github/
│   └── workflows/
│       └── docguard.yml             # GitHub Actions CI workflow
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 🤝 GitHub Actions Integration

DocGuard automatically runs on every Pull Request via [`.github/workflows/docguard.yml`](.github/workflows/docguard.yml). It inspects the PR branch, compares against the target base, and publishes an evidence-based comment:

```text
## 🛡️ DocGuard Documentation Intelligence Report

⚠️ Documentation drift detected! (1 issue found)
Repository Documentation Health: 82%

### Issue #1: `TIMEOUT_SECONDS` in `docs/configuration.md`
Verdict: 🔴 CONFIRMED DRIFT | Confidence: 98%

- Source File: src/config.py
- Documentation File: docs/configuration.md (Line 3)

Outdated Statement in Documentation:
> The request timeout is 30 seconds.

Why this is incorrect:
Value for 'TIMEOUT_SECONDS' was changed from '30' to '60' in src/config.py, but documentation still states '30'.

Related Code Diff:
```diff
- TIMEOUT_SECONDS = 30
+ TIMEOUT_SECONDS = 60
```

Suggested Correction:
> The request timeout is 60 seconds.
```

---

## 📄 License
MIT License. Built for developers who care about truthful documentation.
