# ratchet — project notes

Global rules in `~/.claude/CLAUDE.md` apply. This file records only what is
specific to this repo and expensive to rediscover.

## Developing and releasing

ratchet installs from the GitHub marketplace (`joshuarcarlile-cpu/ratchet`).
Claude Code copies `plugin/` at the pinned version into
`~/.claude/plugins/cache/ratchet-marketplace/ratchet/<version>/` and runs it
from there, so an edit in this repo reaches no session until it is released.

- **Test the working copy:** start a session with
  `claude --plugin-dir C:\Users\joshu\Projects\ratchet\plugin`, which overrides
  the installed copy for that session. Each hook firing re-reads its script,
  so script edits are live on the next tool call; `hooks.json` is read once at
  session start, so changing *which* hooks exist needs a new session.
- **Release:** bump `version` in `plugin/.claude-plugin/plugin.json`, push
  `master`, then run `claude plugin marketplace update ratchet-marketplace`
  and `claude plugin update ratchet@ratchet-marketplace`. Sessions already
  running keep the old hooks until they restart.

Never copy the working tree into the cache: that rewrites a pinned release in
place, so every session on the machine runs unreleased code.

## Testing

Check command is in `.claude/PROJECT_PROFILE.md`. Use the
`PYTHONDONTWRITEBYTECODE` env var rather than `py -3 -B`: the suite runs hook
scripts as subprocesses, and a subprocess inherits the env var but not the flag.

## Line endings

`.gitattributes` forces LF everywhere except `*.ps1`, which is CRLF. A CRLF
shebang makes `ratchet-hook.sh` fail on Linux with "bad interpreter". Keep new
shell and Python files LF.
