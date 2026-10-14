---
max_turns: 8
allowed_tools: [Read, Glob, Grep, Edit, Write]
---

Two small edits, in this order.

1. In docs/changelog.md, add the line `- Probe uptime` under `## Unreleased`.
2. In scripts/server/router_probes.sh, add the line `probe "uptime" uptime` after the existing `probe "date" date` line.

Make only these two edits, then stop.
