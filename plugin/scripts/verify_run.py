#!/usr/bin/env python3
"""Run the project's check command and record the result.

The point of running the check *through* this script is that the receipt is
written by whatever actually executed the command. Claude cannot record a pass
by asserting one — only a real zero exit clears the gate that
require_verification.py holds.

Usage:
    verify_run.py --command "<the check command>"
    verify_run.py --session <id> --command "<the check command>"

The command is taken as one string rather than as trailing argv, deliberately.
Re-joining split arguments with spaces loses their quoting — `pytest -k "not
slow"` comes back as four words and the shell re-splits it — so the command is
never round-tripped through a split/join at all.

Output is streamed through unchanged, and this script exits with the command's
own exit code so the caller sees the real result.
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hook_io  # noqa: E402
import session_state  # noqa: E402


def parse_args(argv):
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--session", default=None)
    parser.add_argument("--command", default=None)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    command_text = (args.command or "").strip()
    if not command_text:
        print(
            "ratchet: no check command given "
            '(usage: verify_run.py --command "<command>")',
            file=sys.stderr,
        )
        return 2

    # An unsubstituted `${CLAUDE_SESSION_ID}` means the caller's placeholder did
    # not expand. Recorded as unknown rather than stored as a literal, since it
    # is diagnostic only — the gate matches on timestamps, not session identity.
    session = args.session
    if not session or "${" in session:
        session = os.environ.get("CLAUDE_SESSION_ID") or None

    # shell=True so the profile's command works as written (`npm test`,
    # `pytest -q`, `.\gradlew.bat :app:test`). It runs in the platform's default
    # shell, which is the constraint the profile's command has to satisfy.
    try:
        completed = subprocess.run(command_text, shell=True)
        exit_code = completed.returncode
    except OSError as exc:
        print(f"ratchet: could not run `{command_text}`: {exc}", file=sys.stderr)
        exit_code = 127

    session_state.record_verification(
        command=command_text, exit_code=exit_code, session=session
    )

    if exit_code == 0:
        hook_io.note(f"ratchet: verified — `{command_text}` passed.")
    else:
        hook_io.note(
            f"ratchet: `{command_text}` exited {exit_code}. "
            "The verification gate stays armed until it passes."
        )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
