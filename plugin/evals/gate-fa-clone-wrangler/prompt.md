---
max_turns: 8
model: claude-haiku-5-5
allowed_tools: [Read, Glob, Grep, Edit, Write]
---

Two small edits, in this order.

1. In CHANGELOG.md, add the line `- Add notes` under `## Unreleased`.
2. Create a new file NOTES.md whose only line is `Worker: <name>`, where `<name>` is the `name` value in website/wrangler.toml.

Make only these two edits, then stop.
