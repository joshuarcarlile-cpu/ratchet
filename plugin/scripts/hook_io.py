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

import hashlib
import json
import os
import re
import sys


def read_event():
    """Parse the hook event from stdin.

    Returns an empty dict when stdin is empty or unparseable, so a malformed
    event degrades to "this hook has nothing to say" rather than a traceback.
    A hook that crashes is a hook that blocks the user's tool call.

    Claude Code sends UTF-8. Reading the bytes and decoding them here means a
    non-ASCII path survives even when Python's own stdin encoding is the
    Windows code page, which it is for a pipe unless UTF-8 mode is on.
    """
    try:
        stream = getattr(sys.stdin, "buffer", None)
        if stream is None:
            raw = sys.stdin.read()
        else:
            raw = stream.read().decode("utf-8", errors="replace")
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


def data_dir():
    """`${CLAUDE_PLUGIN_DATA}`, where ratchet keeps its state, or None.

    State used to live in `<project>/.claude/framework/`, which broke
    `git clone <url> .` into a fresh folder: the first tool call created the
    folder, so it was no longer empty. Nothing is written into the project now.
    """
    return os.environ.get("CLAUDE_PLUGIN_DATA") or None


def _project_key(project):
    """A file name for one project: readable, and stable across spellings.

    `C:/x/proj/` and its backslashed, lower-case spelling are the same folder,
    so the hash is taken over the normalised absolute path. The basename keeps
    the folder findable by eye; the hash keeps two same-named folders apart.
    """
    normalised = os.path.normcase(os.path.abspath(project))
    digest = hashlib.sha1(normalised.encode("utf-8")).hexdigest()[:10]
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", os.path.basename(normalised))[:40]
    return f"{name or 'root'}-{digest}"


def event_log_path(event=None):
    """The project's append-only event log, or None without a data dir."""
    base = data_dir()
    if base is None:
        return None
    return os.path.join(base, "projects", _project_key(project_dir(event)) + ".jsonl")


def tool_log_path():
    """The command log find-patterns reads, shared by every project."""
    base = data_dir()
    return os.path.join(base, "tool-log.jsonl") if base else None


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


def _write_utf8(text):
    """Write to stdout as UTF-8, whatever Python thinks stdout's encoding is.

    A piped stdout on Windows defaults to the ANSI code page, so the em dash
    in a block reason reached Claude Code as byte 0x97 and the transcript
    showed U+FFFD. Writing bytes makes PYTHONUTF8 irrelevant.
    """
    stream = getattr(sys.stdout, "buffer", None)
    if stream is None:
        sys.stdout.write(text)
        sys.stdout.flush()
        return
    sys.stdout.flush()
    stream.write(text.encode("utf-8"))
    stream.flush()


def emit(payload):
    """Write a hook's JSON response to stdout."""
    _write_utf8(json.dumps(payload, ensure_ascii=False))


def note(message):
    """Print an advisory line for the transcript. Not a blocking signal."""
    _write_utf8(message.rstrip("\n") + "\n")
