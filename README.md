# ratchet

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-121%20passed-brightgreen.svg)](plugin/scripts/tests)

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
│   └─ Stop ─────────> finds the code Claude changed           │
│                      no passing check newer than the change? │
│                                                              │
│                      BLOCKED                                 │
│                      "app.py changed this session, and no    │
│                       check has passed."                     │
│                                                              │
│ Claude runs the project's check command                      │
│   └─ exit 0 ───────> receipt recorded, gate clears           │
│   └─ exit 1 ───────> gate stays armed                        │
└──────────────────────────────────────────────────────────────┘
```

## What it does

**Enforced by hooks** — these do not depend on the model cooperating:

- **Verification gate** (`verify` skill + `Stop` hook) — refuses to end a turn on
  code Claude changed without a passing check. A pass is recorded by a hook from
  the shell call's own exit code when Claude runs the profile's Test command, so
  it cannot be *asserted* — only a real zero exit clears the gate. A pipe, `;`
  or `||` after the check hides that exit code, so such runs record nothing.
  Checks the profile can't name go through `verify_run.py --command "<check>"`.
- **What counts as a change** — files Claude wrote with Write, Edit or
  NotebookEdit, and files written during one of its own Bash or PowerShell
  calls, so `sed -i` counts the same as Edit. Files a clone, a checkout, a
  program or your editor produced do not. Neither do prose, dotfiles
  (`.gitignore`, `.env.example`), `*.example`, `*.session`, or extensionless
  files without a shebang (UCI config). TOML, YAML, JSON and HTML do count.
- **File-size warning** (`PostToolUse`) — flags files over a line budget
  (default 400, `RATCHET_FILE_SIZE_THRESHOLD` to change it).
- **Tool-call logging** (`PostToolUse`, async) — records Bash and PowerShell
  command shapes for `find-patterns` to mine.

State lives under the plugin's data directory, `~/.claude/plugins/data/<id>/`,
one event log per project. Nothing is written into your project, so
`git clone <url> .` into a fresh folder works. Folders named
`.claude/framework/` left by ratchet 0.2 are no longer used and can be deleted.

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

Either one runs the hook tests on your machine and validates the manifest — a
hook that mangles its own input is worse than no hook. It registers nothing.
Then install from GitHub:

```
/plugin marketplace add joshuarcarlile-cpu/ratchet
/plugin install ratchet@ratchet-marketplace
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
PYTHONDONTWRITEBYTECODE=1 py -3 -m unittest discover -s plugin/scripts/tests -p "test_*.py"
claude plugin eval plugin --scaffold --allow-tools Write Edit --ablation none
```

`PYTHONDONTWRITEBYTECODE` keeps `__pycache__/` out of `plugin/`, and unlike
`-B` it reaches the hook scripts the tests run as subprocesses.

The `gate` eval cases replay the 20 blocks the October 2026 config audit
recorded: each case's description says which ones it stands for. The six
false-alarm cases must not block and the four real catches must. Their graders
are regexes, so the suite costs only the agent runs. Eval runs can't grant Bash
on native Windows, so every edit in them goes through Write or Edit.

Each case pins its model: the `gate` cases run on Haiku, because the hook
decides those and the model only makes an edit; the skill cases run on Sonnet,
because Haiku never invokes plan-first or minimalism, with or without this
plugin. Passing `--model` overrides every pin. Add `--tag gate` to run the gate
cases alone.

Unit tests cover hook logic deterministically. Evals grade model behaviour. The
eval tier cannot catch a hook that mangles its own input, and the unit tier
cannot catch a hook that emits a correctly-shaped block Claude Code ignores —
both classes of bug have shipped here, and each was caught by the tier the other
one missed.

**The gate is escapable on purpose.** It stands down after two nudges rather than
trapping a session that genuinely cannot satisfy it, ignores files that aren't
code, and only ever considers what Claude changed in the current session. Its job is to make skipping verification a deliberate act, not an
impossible one.

## Local development

```bash
claude --plugin-dir ./plugin
```

It overrides the installed copy for that session only. Then `/reload-plugins`
after editing any skill, hook, or agent file.

Don't register this folder as a marketplace to test it: a local folder source
loads the working copy in place, so every session on the machine would run
whatever is half-edited here.

## Credits

Structure — Python logic behind thin shell dispatchers, deterministic tests with
edge-case fixtures, and reporting the provenance of a heuristic's own numbers —
follows [antigravity-usage](https://github.com/joshuarcarlile-cpu/antigravity-usage).

## License

MIT. See [LICENSE](LICENSE).
