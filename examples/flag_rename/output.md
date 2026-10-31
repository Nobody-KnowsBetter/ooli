<!-- Produced by examples/run_example.py with qwen2.5-coder:3b. -->
## 🛡️ DocGuard Documentation Intelligence Report

⚠️ **Documentation drift detected! (3 issues found)**

Repository Documentation Health: **46%**

---
### Issue #1: `--timeout` in `README.md`

**Verdict**: 🔴 CONFIRMED DRIFT &nbsp;|&nbsp; **Confidence**: `97%`

- **Source File**: `cli.py`
- **Documentation File**: `README.md` (Line 3)

**Outdated Statement in Documentation:**
> Use --timeout to stop slow jobs.

**Why this is incorrect:**
Flag '--timeout' was renamed to '--deadline' in cli.py:4, but this sentence still says '--timeout'.

**Related Code Diff:**
```diff
- add_argument("--timeout")
+ add_argument("--deadline")
```

**Suggested Correction:**
> Use --deadline to stop slow jobs.

**Supporting Evidence:**
- Source code: cli.py:4
- Diff: - add_argument("--timeout")
+ add_argument("--deadline")

---
### Issue #2: `--retries` in `README.md`

**Verdict**: 🔴 CONFIRMED DRIFT &nbsp;|&nbsp; **Confidence**: `97%`

- **Source File**: `cli.py`
- **Documentation File**: `README.md` (Line 5)

**Outdated Statement in Documentation:**
> `--retries` defaults to 3.

**Why this is incorrect:**
The default of '--retries' changed from '3' to '5' in cli.py, but this sentence still says '3'.

**Related Code Diff:**
```diff
--retries default: 3 -> 5
```

**Suggested Correction:**
> `--retries` defaults to 5.

**Supporting Evidence:**
- Source code: cli.py:5
- Diff: --retries default: 3 -> 5

---
### Issue #3: `CACHE_TTL` in `README.md`

**Verdict**: 🔴 CONFIRMED DRIFT &nbsp;|&nbsp; **Confidence**: `85%`

- **Source File**: `cli.py`
- **Documentation File**: `README.md` (Line 7)

**Outdated Statement in Documentation:**
> Finished results stay available for 300 seconds.

**Why this is incorrect:**
'CACHE_TTL' changed from '300' to '900'. qwen2.5-coder:3b confirmed this sentence is about that setting.

**Related Code Diff:**
```diff
- CACHE_TTL = 300
+ CACHE_TTL = 900
```

**Suggested Correction:**
> Finished results stay available for 900 seconds.

**Supporting Evidence:**
- Source code: cli.py:7
- Diff: - CACHE_TTL = 300
+ CACHE_TTL = 900
- Documentation README.md:7 says '300' and not '900'
- qwen2.5-coder:3b: this sentence describes CACHE_TTL

---

💡 *Run `python backend/src/docguard.py --autofix` or approve suggestions in the DocGuard Dashboard to apply fixes.*
