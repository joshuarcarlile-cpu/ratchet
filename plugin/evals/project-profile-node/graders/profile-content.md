---
type: llm
focus: trace
---

PASS if Claude correctly identifies this as a Node/JavaScript project (from package.json) and identifies the test command as `npm test` (or equivalently `jest`, its underlying test runner) — whether or not the actual file write succeeded.
FAIL if Claude misidentifies the language or the test command.
