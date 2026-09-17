# ratchet

A Claude Code plugin that adds workflow discipline on top of whatever project it's installed in — language-agnostic, because it changes how Claude works rather than writing application code itself.

## What it does

- **`project-profile` skill** — detects the host project's language, test/lint/build commands, and conventions, and records them in `.claude/PROJECT_PROFILE.md` so other components don't re-detect from scratch.
- **`plan-first` skill** — enforces explore → plan → review → implement → verify for non-trivial changes, with a mandatory verification check defined before any code is written.
- **`minimalism` skill** — a YAGNI decision ladder Claude applies before writing new code, to avoid over-building.
- **File-size hook** — warns when an edited file crosses a line-count threshold (default 400, override with `RATCHET_FILE_SIZE_THRESHOLD`), so files stay slim and context/drift stays manageable.
- **`log-fix` skill + `regression-writer` subagent** — after a bug fix is verified, writes a regression test in the project's own test framework and appends a one-line gotcha note to the profile.
- **Tool-call logging hook + `find-patterns` skill** — logs Bash command shapes to `.claude/framework/tool-log.jsonl`; `find-patterns` flags sequences repeated often enough to be worth turning into a script.

## Install

```
/plugin marketplace add <owner>/ratchet
/plugin install ratchet
```

## Local development

```bash
claude --plugin-dir ./plugin
```

Then `/reload-plugins` after editing any skill, hook, or agent file.
