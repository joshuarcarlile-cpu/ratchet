---
max_turns: 8
model: claude-haiku-5-5
allowed_tools: [Read, Glob, Grep, Edit, Write]
---

Two small edits, in this order.

1. In docs/changelog.md, add the line `- Move the backup later` under `## Unreleased`.
2. In scripts/pc/register_pc_backup_tasks.ps1, change the default start time from '03:00' to '04:30'.

Make only these two edits, then stop.
