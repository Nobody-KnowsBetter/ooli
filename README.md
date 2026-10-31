# ooli

Finds the sentences in your docs that a pull request probably made wrong, and
points to the code change responsible.

## Run it

You need Python 3.11+, Node.js 18+ and [Ollama](https://ollama.com). Start the Ollama app, then:

```bash
./scripts/dev.sh
```

Open http://localhost:3000, add a public GitHub repository on the Repositories page, and scan its last commit or a pull request. The first run downloads the 2 GB model. Without Ollama, scans still work with rules only.

## How it works

1. **Find what changed.** `ast` compares the old and new Python: constants, function names and parameters, routes, env vars, and CLI flags. Tests and private names are skipped.
2. **Find sentences that may depend on it.** Docs are read at the commit being scanned, skipping changelogs and migration guides.
3. **Decide.** Rules decide exact matches. If a sentence has the old value but doesn't name the setting, Qwen 2.5 Coder 3B decides if it's about that setting.
4. **Report.** The check names the exact sentence, the code change and a suggested fix.

See [examples/](examples/) for real input and output.

## Run the tests

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]" -r backend/requirements.txt
pytest
```

## How we work

1. Create a branch and open a pull request. Never push straight to `main`.
2. Merge only when CI passes.
3. End every commit message with the coding agent and the models we use:

```text
Add tests for URL parser

Coding agent: Claude Code
Models used in project: Qwen 2.5 Coder 3B
```
