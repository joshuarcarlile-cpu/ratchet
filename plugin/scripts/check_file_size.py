#!/usr/bin/env python3
"""PostToolUse(Write|Edit|NotebookEdit) hook: record the edit, warn on size.

Two jobs, one hook, because both need the same event and adding a second script
on the same matcher would double the per-edit cost for no gain:

1. Record that Claude changed a code file, arming the verification gate that
   require_verification.py holds at Stop.
2. Warn when a file crosses a line budget — advisory only. Large files cost
   context on every read and are where drift accumulates, but only the author
   can judge whether a given file has earned its length. Notebooks are JSON,
   so their line count says nothing and they get no warning.

Never blocks an edit.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hook_io  # noqa: E402
import session_state  # noqa: E402

DEFAULT_THRESHOLD = 400


def threshold():
    """Line budget, overridable per project. A non-numeric value is ignored
    rather than crashing the hook on every single edit."""
    raw = os.environ.get("RATCHET_FILE_SIZE_THRESHOLD")
    if not raw:
        return DEFAULT_THRESHOLD
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_THRESHOLD
    return value if value > 0 else DEFAULT_THRESHOLD


def count_lines(path):
    """Line count, or None if the file cannot be read as text."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return sum(1 for _ in handle)
    except (OSError, UnicodeDecodeError):
        return None


def main():
    event = hook_io.read_event()
    path = hook_io.tool_input(event, "file_path")
    notebook = hook_io.tool_input(event, "notebook_path")
    edited = path if isinstance(path, str) and path else notebook
    if not edited or not isinstance(edited, str):
        return 0

    # Arm the verification gate. Done before the isfile() check because an
    # edit counts whether or not the file is still readable from here.
    try:
        session_state.record_edit(edited, event)
    except OSError:
        pass

    if edited != path or not os.path.isfile(path):
        return 0

    limit = threshold()
    lines = count_lines(path)
    if lines is not None and lines > limit:
        hook_io.note(
            f"ratchet: {path} is {lines} lines (threshold {limit}) "
            "— consider splitting it."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
