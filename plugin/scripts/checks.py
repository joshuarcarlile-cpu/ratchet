#!/usr/bin/env python3
"""Recognise a check run in a Bash or PowerShell tool call.

Two kinds of command count as a check:

- the first backticked command on the `- Test:` line of
  `.claude/PROJECT_PROFILE.md`, run as written;
- `verify_run.py --command "<X>"`, which counts as a run of X. It covers checks
  a profile cannot name, such as `bash -n` on whichever script changed.

A shell call reports one exit status, and it is the check's only when nothing
after the check can replace it. `check | tail`, `check; echo done` and
`check || true` all succeed whatever the check did, so they record nothing.
`check && next` succeeding does mean the check passed, but its failure could be
`next`'s, so it records a pass and never a failure.
"""

import os
import re
import shlex

FULL = "full"            # the call's exit status is the check's own
PASS_ONLY = "pass"       # success implies the check passed; failure says nothing

_TEST_LINE = re.compile(r"^\s*[-*]\s*Test:\s*(.*)$", re.IGNORECASE)
_BACKTICKED = re.compile(r"`([^`]+)`")
_EXIT_CODE = re.compile(r"\s*Exit code (-?\d+)")
# Trailing redirections keep the exit status: `2>&1`, `> out.txt`, `2>$null`.
_REDIRECTS = re.compile(r"(?:\s+(?:\d|&|\*)?>{1,2}\s*(?:&\d+|\S+))+\s*$")
# What may precede the check inside its own segment: env assignments, and
# PowerShell's call operator.
_PREFIX = re.compile(r"^(?:&\s*|[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*$")


def profiled_check(project):
    """The profile's Test command, or None if it records none."""
    path = os.path.join(project, ".claude", "PROJECT_PROFILE.md")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return None
    for line in lines:
        match = _TEST_LINE.match(line)
        if match:
            command = _BACKTICKED.search(match.group(1))
            return command.group(1).strip() if command else None
    return None


def _segments(command):
    """Split a command line at top-level control operators.

    Returns [(text, operator_before)], respecting quotes. `&` after `>` or
    before `>` is a redirection (`2>&1`, `&>`), and `&` at the start of a
    segment is PowerShell's call operator; neither splits.
    """
    segments, buf, op_before, quote = [], [], None, None
    i, n = 0, len(command)
    while i < n:
        c = command[i]
        if quote:
            buf.append(c)
            if c == "\\" and quote == '"' and i + 1 < n:
                buf.append(command[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "'\"":
            quote = c
        elif c == "\\" and i + 1 < n:
            buf.append(c)
            buf.append(command[i + 1])
            i += 2
            continue
        elif command.startswith(("&&", "||"), i):
            segments.append(("".join(buf), op_before))
            buf, op_before = [], command[i:i + 2]
            i += 2
            continue
        elif c in "|;\n" or (
            c == "&"
            and "".join(buf).strip()
            and not "".join(buf).rstrip().endswith(">")
            and command[i + 1:i + 2] != ">"
        ):
            segments.append(("".join(buf), op_before))
            buf, op_before = [], c
            i += 1
            continue
        buf.append(c)
        i += 1
    segments.append(("".join(buf), op_before))
    # A blank segment after `;` or a newline is just a trailing separator.
    return [
        (text, op) for text, op in segments
        if text.strip() or op not in (None, ";", "\n")
    ]


def _normalise(text):
    text = re.sub(r"\s+", " ", text.replace("\\", "/")).strip()
    return re.sub(r"(^|\s)\./", r"\1", text)


def _verdict(segments, index):
    """FULL, PASS_ONLY or None, from the operators around one segment."""
    if segments[index][1] == "||":
        return None
    after = segments[index + 1][1] if index + 1 < len(segments) else None
    if after is None:
        return FULL
    if after == "&&":
        return PASS_ONLY
    return None


def attribution(command, check):
    """How far `command`'s exit status speaks for `check`, or None."""
    target = _normalise(check or "")
    if not target or not command:
        return None
    segments = _segments(command)
    for index, (text, _) in enumerate(segments):
        body = _normalise(_REDIRECTS.sub("", text))
        if not body.endswith(target):
            continue
        prefix = body[: len(body) - len(target)]
        if prefix and not prefix.endswith(" "):
            continue
        if not _PREFIX.match(prefix):
            continue
        verdict = _verdict(segments, index)
        if verdict:
            return verdict
    return None


def verify_run_target(command):
    """(inner command, verdict) for a `verify_run.py --command X` call."""
    if not command or "verify_run.py" not in command:
        return None
    segments = _segments(command)
    for index, (text, _) in enumerate(segments):
        at = text.find("verify_run.py")
        if at < 0:
            continue
        try:
            tokens = shlex.split(_REDIRECTS.sub("", text[at:]), posix=True)
        except ValueError:
            continue
        inner = None
        for position, token in enumerate(tokens):
            if token == "--command" and position + 1 < len(tokens):
                inner = tokens[position + 1]
            elif token.startswith("--command="):
                inner = token[len("--command="):]
        verdict = _verdict(segments, index)
        if inner and inner.strip() and verdict:
            return inner.strip(), verdict
    return None


def result(event, project):
    """(check command, exit code) if this shell call was a check, else None."""
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command")
    if not isinstance(command, str) or tool_input.get("run_in_background"):
        return None

    if event.get("hook_event_name") == "PostToolUseFailure":
        match = _EXIT_CODE.match(str(event.get("error") or ""))
        if not match:
            return None
        exit_code = int(match.group(1))
    else:
        response = event.get("tool_response")
        if isinstance(response, dict) and response.get("interrupted"):
            return None
        exit_code = 0

    candidates = []
    check = profiled_check(project)
    if check:
        candidates.append((check, attribution(command, check)))
    runner = verify_run_target(command)
    if runner:
        candidates.append(runner)
    for name, verdict in candidates:
        if verdict == FULL or (verdict == PASS_ONLY and exit_code == 0):
            return name, exit_code
    return None
