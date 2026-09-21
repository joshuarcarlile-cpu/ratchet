#!/usr/bin/env python3
"""PostToolUse(Bash) hook: append a command signature to ratchet's tool log.

Logs the command *shape* only, truncated — never tool output. `find-patterns`
reads this log to spot sequences worth turning into a script.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hook_io  # noqa: E402

MAX_COMMAND_LENGTH = 120


def main():
    event = hook_io.read_event()
    command = hook_io.tool_input(event, "command")
    if not command or not isinstance(command, str):
        return 0

    record = {"ts": int(time.time()), "cmd": command[:MAX_COMMAND_LENGTH]}
    log_path = os.path.join(hook_io.framework_dir(event), "tool-log.jsonl")
    try:
        hook_io.append_jsonl(log_path, record)
    except OSError:
        # A hook that cannot write its log has nothing useful to say about it.
        # Failing loudly here would interrupt the user's actual work.
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
