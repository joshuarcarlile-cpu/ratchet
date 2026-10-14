#!/usr/bin/env python3
"""PostToolUse / PostToolUseFailure (Bash|PowerShell) hook: record a shell call.

Three records, all appends:

1. The command shape, truncated, to `${CLAUDE_PLUGIN_DATA}/tool-log.jsonl` for
   `find-patterns`. Never tool output.
2. The call's time window, so the Stop gate can tell which files Claude's own
   shell wrote.
3. A check result, when the call ran the project's check command (see
   checks.py). This is what clears the gate: a passing run needs no wrapper.

Runs async. It decides nothing, and the Stop hook only reads its records after
a full model response, by which time they have long landed.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import checks  # noqa: E402
import hook_io  # noqa: E402
import session_state  # noqa: E402

MAX_COMMAND_LENGTH = 120

# The log is shared by every project and find-patterns reads only its recent
# window, so once it passes MAX_LOG_BYTES it keeps the newest KEEP_LINES lines.
# At 120 characters a command, KEEP_LINES fits well under the cap.
MAX_LOG_BYTES = 1_000_000
KEEP_LINES = 2000


def trim(path):
    """Cut the log back to its newest lines once it outgrows its cap.

    The rewrite can drop a line another hook appends at the same moment, which
    for a pattern log costs nothing worth a lock.
    """
    try:
        if os.path.getsize(path) <= MAX_LOG_BYTES:
            return
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()[-KEEP_LINES:]
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.writelines(lines)
        os.replace(tmp, path)
    except OSError:
        pass


def main():
    event = hook_io.read_event()
    command = hook_io.tool_input(event, "command")
    if not command or not isinstance(command, str):
        return 0

    log = hook_io.tool_log_path()
    if log is None:
        return 0
    project = hook_io.project_dir(event)
    try:
        hook_io.append_jsonl(log, {
            "ts": int(time.time()),
            "cmd": command[:MAX_COMMAND_LENGTH],
            "project": project,
        })
        trim(log)
        session_state.record_shell(command, event)
        outcome = checks.result(event, project)
        if outcome:
            session_state.record_check(outcome[0], outcome[1], event)
    except OSError:
        # A hook that cannot write its log has nothing useful to say about it.
        # Failing loudly here would interrupt the user's actual work.
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
