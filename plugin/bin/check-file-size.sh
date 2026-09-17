#!/usr/bin/env bash
# Reads PostToolUse hook JSON on stdin, extracts .tool_input.file_path, and
# warns if that file is over the line-count threshold. Exit 0 always.
threshold="${RATCHET_FILE_SIZE_THRESHOLD:-400}"
input="$(cat)"

if command -v jq >/dev/null 2>&1; then
  file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
else
  # Fallback when jq isn't installed: regex-extract the field. The hook JSON
  # is Claude Code's own output, not arbitrary user input, so this is safe.
  file=$(printf '%s' "$input" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | sed -E 's/.*:[[:space:]]*"(.*)"/\1/')
fi

[ -n "$file" ] && [ -f "$file" ] || exit 0
lines=$(wc -l < "$file" | tr -d ' ')
if [ "$lines" -gt "$threshold" ]; then
  echo "ratchet: $file is $lines lines (threshold $threshold) — consider splitting it."
fi
exit 0
