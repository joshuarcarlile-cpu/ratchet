#!/usr/bin/env python3
"""Shared I/O for ratchet's Claude Code hooks.

A hook receives one JSON object on stdin and may emit one JSON object on stdout.
Both directions go through the `json` module here, deliberately: ratchet
previously extracted fields with the regex `"command"\\s*:\\s*"[^"]*"` and built
its output lines with printf. `[^"]*` stops at the first *escaped* quote inside a
JSON string, so any command containing a quote was truncated mid-escape — and the
truncated line was still valid JSON, so downstream readers counted it as a real
command rather than skipping it.

Nothing in this module hand-rolls JSON. New hooks should use it rather than
re-deriving the parsing.
"""

import json
import os
import sys


def read_event():
    """Parse the hook event from stdin.

    Returns an empty dict when stdin is empty or unparseable, so a malformed
    event degrades to "this hook has nothing to say" rather than a traceback.
    A hook that crashes is a hook that blocks the user's tool call.
    """
    try:
        raw = sys.stdin.read()
    except (OSError, UnicodeDecodeError):
        return {}
    if not raw.strip():
        return {}
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return event if isinstance(event, dict) else {}


def tool_input(event, field, default=None):
    """Read one field out of the event's tool_input, tolerating a missing shape."""
    value = event.get("tool_input")
    if not isinstance(value, dict):
        return default
    return value.get(field, default)


def project_dir(event=None):
    """The project root — anchored, never inherited from the shell's cwd.

    Hooks inherit the Bash tool's *persisted* working directory, which is not
    always the project root. Anchoring on a relative path is what scattered
    ratchet's tool log into stray `.claude/framework/` trees, one per directory
    the shell happened to be sitting in.

    Order: the environment variable Claude Code sets, then the event's own cwd,
    then this file's location (fixed, unlike the cwd), then the cwd as a last
    resort.
    """
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return env
    if isinstance(event, dict):
        cwd = event.get("cwd")
        if cwd:
            return cwd
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        return plugin_root
    return os.getcwd()


def framework_dir(event=None, create=False):
    """`<project>/.claude/framework`, where ratchet keeps its own state.

    Every hook that writes here creates the folder through `create=True`, which
    also gives it its own `.gitignore` of `*`, the way `.pytest_cache` does. The
    contents are per-machine bookkeeping, so no project should need an ignore
    entry of its own to keep them out of a commit.
    """
    path = os.path.join(project_dir(event), ".claude", "framework")
    if create:
        os.makedirs(path, exist_ok=True)
        _ignore_self(path)
    return path


def _ignore_self(path):
    """Give a folder a `.gitignore` of `*` if it has none. Best-effort.

    Exclusive-create mode never overwrites a file that is already there, and a
    failure is swallowed: a marker that cannot be written must not cost the
    hook the state it was about to save.
    """
    try:
        with open(os.path.join(path, ".gitignore"), "x", encoding="utf-8") as handle:
            handle.write("# Created by ratchet: local state, never committed.\n*\n")
    except OSError:
        pass


def append_jsonl(path, record):
    """Append one record as a JSON line. Encoding is the json module's problem."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path):
    """Read a .jsonl file, yielding (record, ok) pairs.

    Malformed lines yield (raw_line, False) instead of being dropped, so a
    caller can *report* how many entries it could not parse. Silently skipping
    them would trade one wrong answer for a differently wrong answer; the log's
    provenance is part of its meaning.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except (OSError, UnicodeDecodeError):
        return []

    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            out.append((line, False))
            continue
        out.append((record, isinstance(record, dict)))
    return out


def emit(payload):
    """Write a hook's JSON response to stdout."""
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.flush()


def note(message):
    """Print an advisory line for the transcript. Not a blocking signal."""
    sys.stdout.write(message.rstrip("\n") + "\n")
    sys.stdout.flush()
