---
max_turns: 8
allowed_tools: [Read, Glob, Grep, Edit, Write]
---

Two small edits, in this order.

1. In CHANGELOG.md, add the line `- Document the session file` under `## Unreleased`.
2. In README.md, add a sentence saying the bot keeps its Telegram login in tg_dedupe_session.session, which must never be committed.

Make only these two edits, then stop.
