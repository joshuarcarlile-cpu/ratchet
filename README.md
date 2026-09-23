# ratchet

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-53%20passed-brightgreen.svg)](plugin/scripts/tests)

Workflow discipline for **Claude Code**, as mechanism rather than advice.

A ratchet is a thing that stops you sliding backwards. Most workflow tooling is
prose the model may or may not follow; this enforces the parts that can be
enforced, and is honest about the parts that cannot.

```text
┌──────────────────────────────────────────────────────────────┐
│ Claude edits app.py                                          │
│   └─ PostToolUse ──> records the change, warns on file size  │
│                                                              │
│ Claude tries to end the turn                                 │
│   └─ Stop ─────────> scans the worktree for changed code     │
│                      no passing check newer than the change? │
│                                                              │
│                      BLOCKED                                 │
│                      "app.py changed this session, and no    │
│                       check has passed."                     │
│                                                              │
│ Claude runs the project's check through ratchet's runner     │
│   └─ exit 0 ───────> receipt recorded, gate clears           │
│   └─ exit 1 ───────> gate stays armed                        │
└──────────────────────────────────────────────────────────────┘
```

## What it does

**Enforced by hooks** — these do not depend on the model cooperating:

- **Verification gate** (`verify` skill + `Stop` hook) — refuses to end a turn on
  code that changed without a passing check. The check runs through ratchet's own
  runner, which writes the receipt, so a pass cannot be *asserted* — only a real
  zero exit clears the gate. Change detection scans the filesystem, not tool
  events, so an edit made through Bash counts the same as one made through Edit.
- **File-size warning** (`PostToolUse`) — flags files over a line budget
  (default 400, `RATCHET_FILE_SIZE_THRESHOLD` to change it).
- **Tool-call logging** (`PostToolUse`, async) — records Bash and PowerShell
  command shapes for `find-patterns` to mine.

State lives in the project's `.claude/framework/`, which carries its own
`.gitignore` of `*`, so it never needs an ignore entry of your own.

**Guidance for the model** — skills it applies when they're relevant:

- **`project-profile`** — detects the host project's language, test/lint/build
  commands and conventions, and records them in `.claude/PROJECT_PROFILE.md` so
  nothing else re-detects from scratch. The verification gate reads its check
  command from here.
- **`plan-first`** — explore → plan → review → implement → verify for non-trivial
  changes, with the verification step named before any code is written.
- **`minimalism`** — a YAGNI ladder applied before writing new code.
- **`log-fix`** + **`regression-writer` subagent** — after a fix is verified,
  writes a regression test in the project's own framework and appends a one-line
  gotcha to the profile.
- **`find-patterns`** — flags command sequences repeated often enough to be worth
  turning into a script.

## Install

```bash
./install.sh          # macOS / Linux
```
```powershell
.\install.ps1         # Windows
```

Either one verifies the hooks work on your machine before registering anything —
a hook that mangles its own input is worse than no hook. Then:

```
/plugin install ratchet
```

Or skip the installer and use the marketplace directly:

```
/plugin marketplace add joshuarcarlile-cpu/ratchet
/plugin install ratchet
```

Run `/project-profile` once per project so the gate knows your check command.

## Design

**Logic in Python, shells thin.** `plugin/scripts/*.py` holds everything real;
`plugin/bin/ratchet-hook.sh` only locates a script and an interpreter. Hook I/O
goes through the `json` module in both directions. An earlier version parsed hook
input with `[^"]*` and built its output with `printf`, which silently truncated
any command containing a quote — and the truncated line was still valid JSON, so
the one skill that read the log counted it as real. Nothing here hand-rolls JSON.

This also settles portability: Python runs the same on Windows, macOS and Linux,
so there is one implementation rather than parallel `.sh` and `.ps1` versions of
the same logic.

**Two tiers of tests, because they catch different things.**

```bash
python -B -m unittest discover -s plugin/scripts/tests -p "test_*.py"
claude plugin eval
```

`-B` keeps `__pycache__/` out of `plugin/` (the tests' own subprocesses set
`PYTHONDONTWRITEBYTECODE`): the marketplace installs from this working tree,
gitignored files included, so bytecode from a test run would ship.

Unit tests cover hook logic deterministically. Evals grade model behaviour. The
eval tier cannot catch a hook that mangles its own input, and the unit tier
cannot catch a hook that emits a correctly-shaped block Claude Code ignores —
both classes of bug have shipped here, and each was caught by the tier the other
one missed.

**The gate is escapable on purpose.** It stands down after two nudges rather than
trapping a session that genuinely cannot satisfy it, ignores prose files and
ratchet's own bookkeeping, and only ever considers work done since the session
started. Its job is to make skipping verification a deliberate act, not an
impossible one.

## Local development

```bash
claude --plugin-dir ./plugin
```

Then `/reload-plugins` after editing any skill, hook, or agent file.

To rehearse the real marketplace flow without pushing:

```
/plugin marketplace add /absolute/path/to/this/repo
/plugin install ratchet
```

## Credits

Structure — Python logic behind thin shell dispatchers, deterministic tests with
edge-case fixtures, and reporting the provenance of a heuristic's own numbers —
follows [antigravity-usage](https://github.com/joshuarcarlile-cpu/antigravity-usage).

## License

MIT. See [LICENSE](LICENSE).
