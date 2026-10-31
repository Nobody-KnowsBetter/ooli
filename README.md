# ooli

Finds the sentences in your docs that a pull request probably made wrong, and
points to the code change responsible.

## Use it on your repository

Sign in on the website and click **Add to GitHub Actions** on a repository. DocGuard opens a setup pull request, and once you merge it, every pull request gets checked. You can also add `.github/workflows/docguard.yml` yourself:

```yaml
name: DocGuard

# Runs on pull requests from forks too, so outside contributors see the report.
# DocGuard only reads the pull request's code. It never runs it.
on:
  pull_request_target:

permissions:
  contents: read
  pull-requests: write

jobs:
  docguard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: Nobody-KnowsBetter/ooli@main
```

Every pull request now gets a comment naming the exact doc sentences it made wrong, the code change responsible, a suggested fix and a link to fix it in that pull request. There's no comment when nothing drifted. Everything runs inside your own GitHub Actions: no account, no API key, and your code stays there.

| Input | Default | What it does |
|---|---|---|
| `use-model` | `true` | Runs Qwen for sentences the rules can't decide. It's only downloaded when one exists. |
| `model` | `qwen2.5-coder:3b` | The Ollama model to use. |
| `comment` | `true` | Posts the report on the pull request. It always appears in the job summary too. |
| `fail-on-drift` | `false` | Fails the check when it confirms drift. |

Outputs: `drift-count`, `confirmed-count`, `possible-count`.

## Run it

You need Python 3.11+, Node.js 18+ and [Ollama](https://ollama.com). Start the Ollama app, then:

```bash
./scripts/dev.sh
```

Open http://localhost:3000 and sign in with GitHub. Your repositories appear on the dashboard by themselves, and open pull requests in recently active ones are checked every two minutes while you're signed in. The first run downloads the 2 GB model. Without Ollama, scans still work with rules only.

### GitHub login

Login is optional. Without it, the dashboard opens directly and you add public repositories by name.

1. Create an OAuth App at https://github.com/settings/developers with the callback URL `http://localhost:3000/api/auth/callback`.
2. Run `./scripts/setup-github-login.sh` and paste the app's client ID and secret. The running backend picks them up by itself.

## Where things are

- `/` is the landing page, plain HTML in `frontend/public/`.
- `/dashboard` is the Next.js app in `frontend/src/app/dashboard/`.
- `/api` is the FastAPI backend in `backend/app/`.

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
