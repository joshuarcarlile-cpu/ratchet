# Project Profile

## Language(s)
- Python 3: `plugin/scripts/*.py` (no marker file — this repo ships a Claude
  Code plugin, not a package, so there is no `pyproject.toml` to detect)
- Bash: `plugin/bin/ratchet-hook.sh`, `install.sh`
- PowerShell 5.1: `install.ps1`, `scripts/sync-plugin.ps1`

## Commands
- Test: `py -3 -m unittest discover -s plugin/scripts/tests -p "test_*.py"`
- Lint/build: none — stdlib only, no build step.

## Conventions
- Tests live in: `plugin/scripts/tests/`
- Scripts live in: `scripts/` (developer tooling), `plugin/scripts/` (hook logic)

## Gotchas
<!-- appended to by the log-fix skill -->
- Hooks execute from the installed plugin cache, never from this repo. Editing
  a hook here changes nothing until `scripts/sync-plugin.ps1` runs. See CLAUDE.md.
- The check command must be valid **cmd.exe**: `verify_run.py` runs it with
  `shell=True`, so PowerShell-only syntax (`$env:X=1; ...`) fails under the
  `verify` skill. Keep it shell-portable.
- A test run drops `__pycache__` into `plugin/scripts/` (gitignored, harmless).
  To avoid it, set `PYTHONDONTWRITEBYTECODE=1` in the environment first — not
  `py -3 -B`: the suite runs hook scripts as subprocesses, which inherit the env
  var but not the flag.
