---
max_turns: 8
model: claude-haiku-5-5
allowed_tools: [Read, Glob, Grep, Edit, Write]
---

Two small edits, in this order.

1. In CHANGELOG.md, add the line `- Force LF line endings` under `## Unreleased`.
2. Create a .gitattributes file with exactly two lines: `*.py text eol=lf` and `*.sh text eol=lf`.

Make only these two edits, then stop.
