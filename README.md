# ooli

Finds the sentences in your docs that a pull request probably made wrong, and
points to the code change responsible.

## Run the tests

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## How we work

1. Create a branch and open a pull request. Never push straight to `main`.
2. Merge only when CI passes.
3. End every commit message with the coding agent and the models we use:

```text
Add tests for URL parser

Coding agent: Claude Code
Models used in project: Qwen 2.5 Coder 7B
```
