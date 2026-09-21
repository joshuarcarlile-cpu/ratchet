#!/usr/bin/env python3
"""Stop hook: refuse to end the turn on unverified edits.

Converts plan-first's step 6 — "Never report a change as complete while the
check is failing or hasn't been run" — from prose into a mechanism. Ratchet
already knows the project's check command; PROJECT_PROFILE.md records it, which
is the entire reason project-profile exists.

The gate is deliberately escapable. A Stop hook that cannot be satisfied traps
the user in a loop with no way out, so this one gives up after
MAX_CONSECUTIVE_BLOCKS nudges on the same batch of edits. Its job is to make
skipping verification a deliberate act, not an impossible one.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hook_io  # noqa: E402
import session_state  # noqa: E402


def build_reason(detail):
    return (
        f"ratchet: this turn edited code without a passing check — {detail}\n\n"
        "Run the project's check command via the `verify` skill (or "
        "`ratchet-hook.sh verify_run.py -- <command>`) and show its real "
        "output before reporting the work complete. If verification genuinely "
        "does not apply here, say so explicitly and stop again."
    )


def main():
    event = hook_io.read_event()

    # Claude Code sets this while already inside a stop-hook continuation.
    # Honour it if present; the block counter below is the real safety net,
    # since this field is not guaranteed across versions.
    if event.get("stop_hook_active"):
        return 0

    blocked, detail = session_state.unverified(event)
    if not blocked:
        return 0

    if not session_state.note_block(event):
        hook_io.note(
            "ratchet: still unverified, but the gate has nudged twice already "
            "— letting this turn end."
        )
        return 0

    # Stop takes `decision`/`reason` at the top level. The nested
    # `hookSpecificOutput` shape is PreToolUse's (`permissionDecision`); using it
    # here emits valid JSON that Claude Code simply ignores, so the hook appears
    # to work while blocking nothing. Verified against 2.1.274.
    hook_io.emit({"decision": "block", "reason": build_reason(detail)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
