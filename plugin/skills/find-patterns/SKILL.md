---
description: Reviews ratchet's log of recent shell commands for sequences repeated often enough to be worth turning into a script. Use on request, or periodically in long sessions.
---

# Find Patterns

1. Find the log. If the user named a log file, read that file, relative to the working directory. Only if they didn't, read `${CLAUDE_PLUGIN_DATA}/tool-log.jsonl` and use the lines whose `project` is this project's root. Each line is one JSON object with a `cmd` field. If there's no log, there's nothing to do.
2. Normalize each `cmd` by stripping literal arguments that vary (specific file paths, numbers, timestamps) to get a command "shape."
3. Group by shape and count occurrences in the recent window (e.g. last 50 entries).
4. For any shape repeated 3 or more times, propose turning it into a script:
   - Location: the scripts directory recorded in `.claude/PROJECT_PROFILE.md` (default `scripts/` if none recorded).
   - Parameterize whatever varied between occurrences (the arguments stripped in step 2).
5. Present the proposal and ask before writing the script — this is judgment-based, not auto-applied. A pattern repeated a few times isn't automatically worth the maintenance cost of a script; use judgment about whether it actually saves more than it costs.
