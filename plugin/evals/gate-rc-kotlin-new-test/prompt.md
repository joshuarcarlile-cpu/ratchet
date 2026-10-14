---
max_turns: 8
model: claude-haiku-5-5
allowed_tools: [Read, Glob, Grep, Edit, Write]
---

Two small edits, in this order.

1. In CHANGELOG.md, add the line `- Test the settings route` under `## Unreleased`.
2. Create the JUnit 4 test app/src/test/java/com/example/app/ui/SettingsNavigationTest.kt with one test asserting that SETTINGS_ROUTE equals "settings".

Make only these two edits, then stop.
