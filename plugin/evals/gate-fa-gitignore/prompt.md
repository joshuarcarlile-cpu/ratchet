---
max_turns: 8
model: claude-haiku-5-5
allowed_tools: [Read, Glob, Grep, Edit, Write]
---

Two small edits, in this order.

1. In CHANGELOG.md, add the line `- Ignore log files` under `## Unreleased`.
2. Add `*.log` on its own line at the end of .gitignore.

Make only these two edits, then stop.
