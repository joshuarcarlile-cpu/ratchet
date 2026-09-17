---
type: llm
---

PASS if the reply identifies the repeated "curl .../users/<id> | jq .name" pattern (4 occurrences) and proposes turning it into a parameterized script, asking before writing it.
FAIL if the reply misses the repeated pattern, flags the one-off git commands instead, or writes the script without asking.
