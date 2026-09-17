#!/usr/bin/env bash
# Reads PostToolUse hook JSON on stdin, appends a one-line command signature
# (truncated, not full output) to .claude/framework/tool-log.jsonl.
input="$(cat)"

if command -v jq >/dev/null 2>&1; then
  cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
else
  cmd=$(printf '%s' "$input" | grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' | sed -E 's/.*:[[:space:]]*"(.*)"/\1/')
fi

[ -n "$cmd" ] || exit 0
cmd="${cmd:0:120}"
mkdir -p .claude/framework
ts=$(date +%s)
# Minimal hand-built JSON line; cmd is truncated shell text, quotes escaped defensively.
esc=$(printf '%s' "$cmd" | sed 's/\\/\\\\/g; s/"/\\"/g')
printf '{"ts":%s,"cmd":"%s"}\n' "$ts" "$esc" >> .claude/framework/tool-log.jsonl
