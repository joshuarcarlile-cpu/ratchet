# ratchet — project notes

Global rules in `~/.claude/CLAUDE.md` apply. This file records only what is
specific to this repo and expensive to rediscover.

## Hooks do not run from this repo

Claude Code copies `plugin/` into the plugin cache at install time and executes
everything from there. `CLAUDE_PLUGIN_ROOT` points at the cache:

    ~/.claude/plugins/cache/ratchet-marketplace/ratchet/<version>/

Editing a hook script here has **no effect on a running session**. Push it live:

```powershell
.\scripts\sync-plugin.ps1
```

Each hook firing re-reads its script from disk, so synced changes under
`scripts/` or `bin/` take effect on the next tool call — no restart. The
exception is `hooks.json`, which the harness reads once at session start:
changing *what* a hook does is live, changing *which* hooks exist is not.

`installLocation` in `known_marketplaces.json` names this repo, which makes it
look like hooks run from here. They do not — that field is the marketplace
source, not the execution root. Verified by probe, not inference.

## Testing

Check command is in `.claude/PROJECT_PROFILE.md`. Use the
`PYTHONDONTWRITEBYTECODE` env var rather than `py -3 -B`: the suite runs hook
scripts as subprocesses, and a subprocess inherits the env var but not the flag.

## Line endings

`.gitattributes` forces LF everywhere except `*.ps1`, which is CRLF. A CRLF
shebang makes `ratchet-hook.sh` fail on Linux with "bad interpreter". Keep new
shell and Python files LF.
