#!/usr/bin/env python3
"""Run a check command and exit with its exit code.

For checks the profile's Test line cannot name, such as `bash -n` on whichever
script changed. The PostToolUse hook that sees this script run reads the
`--command` and records the result, so the receipt still comes from what
actually executed: Claude cannot record a pass by asserting one, only a real
zero exit clears the gate that require_verification.py holds. A check the
profile does name needs no wrapper; running it directly counts the same.

Usage:
    verify_run.py --command "<the check command>"

`--session <id>` is still accepted, for instructions written before 0.3, and
ignored: the hook knows the session.

The command is taken as one string rather than as trailing argv, deliberately.
Re-joining split arguments with spaces loses their quoting — `pytest -k "not
slow"` comes back as four words and the shell re-splits it — so the command is
never round-tripped through a split/join at all.

Output is streamed through unchanged, and this script exits with the command's
own exit code so the caller sees the real result. Piping this script's output
(`| tail`) hides that exit code, and the hook then records nothing.
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hook_io  # noqa: E402


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

    # shell=True so the command works as written (`bash -n x.sh`, `npm test`).
    # It runs in the platform's default shell, cmd.exe on Windows, so the
    # command has to be valid there.
    try:
        completed = subprocess.run(command_text, shell=True)
        exit_code = completed.returncode
    except OSError as exc:
        print(f"ratchet: could not run `{command_text}`: {exc}", file=sys.stderr)
        exit_code = 127

    if exit_code == 0:
        hook_io.note(f"ratchet: `{command_text}` passed.")
    else:
        hook_io.note(
            f"ratchet: `{command_text}` exited {exit_code}. "
            "The verification gate stays armed until it passes."
        )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
