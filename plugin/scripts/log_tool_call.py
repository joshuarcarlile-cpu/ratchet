#!/usr/bin/env python3
"""PostToolUse(Bash|PowerShell) hook: append a command signature to the tool log.

Logs the command *shape* only, truncated — never tool output. `find-patterns`
reads this log to spot sequences worth turning into a script.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hook_io  # noqa: E402
import session_state  # noqa: E402

MAX_COMMAND_LENGTH = 120


def main():
    event = hook_io.read_event()

    # Bash is often the first tool a session touches, and the verification gate
    # needs a session baseline from whichever ratchet hook runs first.
    try:
        session_state.touch_session(event)
    except OSError:
        pass

    command = hook_io.tool_input(event, "command")
    if not command or not isinstance(command, str):
        return 0

    record = {"ts": int(time.time()), "cmd": command[:MAX_COMMAND_LENGTH]}
    try:
        log_dir = hook_io.framework_dir(event, create=True)
        hook_io.append_jsonl(os.path.join(log_dir, "tool-log.jsonl"), record)
    except OSError:
        # A hook that cannot write its log has nothing useful to say about it.
        # Failing loudly here would interrupt the user's actual work.
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
