#!/usr/bin/env bash
# Thin dispatcher: locates a ratchet hook script and an interpreter, then hands
# stdin straight through. All logic lives in ../scripts/*.py — this file exists
# only because hooks.json needs something executable to call.
#
# Usage: ratchet-hook.sh <script-name.py>
set -u

script_name="${1:-}"
if [ -z "$script_name" ]; then
  echo "ratchet-hook: no hook script named" >&2
  exit 0
fi
shift

dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$dir/../scripts/$script_name"

if [ ! -f "$script" ] && [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
  script="$CLAUDE_PLUGIN_ROOT/scripts/$script_name"
fi

if [ ! -f "$script" ]; then
  echo "ratchet-hook: $script_name not found" >&2
  exit 0
fi

# Hooks fire on every edit and every Bash call, and they run from the
# installed plugin directory. Byte-compiling there drops __pycache__/ into
# the plugin cache, which then diverges from source for no benefit: these
# scripts are small and run once per event, so the cache buys nothing.
export PYTHONDONTWRITEBYTECODE=1

# `py -3` first on Windows: `python` there is often the Store shim, which is not
# a working interpreter. Exit 0 on a miss — a hook that cannot run is not a
# reason to fail the user's tool call. The launcher is trusted without a trial
# run: probing it with `py -3 -c ""` started Python twice per hook, about 215 ms
# on every event. A launcher with no Python 3 behind it now shows up as a hook
# error rather than falling through to `python3`.
if command -v py >/dev/null 2>&1; then
  exec py -3 "$script" "$@"
elif command -v python3 >/dev/null 2>&1; then
  exec python3 "$script" "$@"
elif command -v python >/dev/null 2>&1; then
  exec python "$script" "$@"
else
  echo "ratchet-hook: no Python interpreter on PATH" >&2
  exit 0
fi
