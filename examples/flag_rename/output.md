<!-- Produced by examples/run_example.py with qwen2.5-coder:3b. -->
## DocGuard report

This change probably made **3 sentences** in the docs wrong.

### `README.md:3`

> Use --timeout to stop slow jobs.

**Caused by** `cli.py:4`: Flag '--timeout' was renamed to '--deadline' in cli.py:4, but this sentence still says '--timeout'.

**Suggested fix:**

> Use --deadline to stop slow jobs.

### `README.md:5`

> `--retries` defaults to 3.

**Caused by** `cli.py:5`: The default of '--retries' changed from '3' to '5' in cli.py, but this sentence still says '3'.

**Suggested fix:**

> `--retries` defaults to 5.

### `README.md:7`

> Finished results stay available for 300 seconds.

**Caused by** `cli.py:7`: 'CACHE_TTL' changed from '300' to '900'. qwen2.5-coder:3b confirmed this sentence is about that setting.

**Suggested fix:**

> Finished results stay available for 900 seconds.

<sub>Checked by: heuristic, qwen2.5-coder:3b. This check never blocks a merge unless you turn that on.</sub>
