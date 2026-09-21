#!/usr/bin/env python3
"""Ratchet's session state: what was edited, and what was verified.

This is the file that lets a stateless hook answer "did this work get checked?".
Two facts, and a timestamp comparison between them:

    the filesystem   scanned at Stop for the newest changed code file
    last_verification  written by verify_run.py, and only ever by a command
                       that actually exited 0

A verification counts only if it is *newer* than the newest change. Editing
after a green test run re-arms the gate, which is what makes this a ratchet
rather than a checkbox.

The change signal is the filesystem rather than the tool log, because an edit
made through Bash (`printf >> app.py`, `sed -i`, a heredoc) never fires a
Write|Edit hook. A gate you can step around by picking a different tool is
not a gate. `last_edit` is still recorded, but only to enrich the message.

Scope is the project, not the session. State lives in the project's own
`.claude/framework/`, and matching is by timestamp rather than session id.
Two concurrent sessions in one project can therefore satisfy each other's gate —
an accepted trade, because the alternative (strict session matching) blocks real
work whenever a session id fails to thread through, and a false block is far
more costly than a missed nudge.
"""

import json
import os
import subprocess
import time

import hook_io

STATE_FILENAME = "session-state.json"
SCHEMA_VERSION = 1

# Editing prose should not demand a test run. Anything not listed here counts as
# code; erring toward "this needs verifying" is the safer default for a gate.
NON_CODE_SUFFIXES = {".md", ".txt", ".rst", ".adoc", ".log"}

# A Stop hook that cannot be satisfied traps the user in a loop. After this many
# consecutive blocks on the same batch of unverified edits, let the turn end.
MAX_CONSECUTIVE_BLOCKS = 2


def state_path(event=None):
    return os.path.join(hook_io.framework_dir(event), STATE_FILENAME)


def load(event=None):
    """Read state, degrading to an empty record rather than raising.

    A corrupt state file must not break every subsequent tool call, so an
    unreadable one is treated as absent and will be overwritten on next write.
    """
    try:
        with open(state_path(event), "r", encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, ValueError):
        return {"version": SCHEMA_VERSION}
    if not isinstance(state, dict):
        return {"version": SCHEMA_VERSION}
    return state


def save(state, event=None):
    path = state_path(event)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def is_code(path):
    """Whether editing this path should arm the verification gate."""
    if not path:
        return False
    normalised = path.replace("\\", "/")
    # Ratchet's own bookkeeping is not the user's work.
    if "/.claude/" in normalised or normalised.startswith(".claude/"):
        return False
    return os.path.splitext(normalised)[1].lower() not in NON_CODE_SUFFIXES


def record_edit(path, event=None, now=None):
    """Note that a source file changed. Re-arms the gate."""
    if not is_code(path):
        return False
    state = load(event)
    previous = state.get("last_edit") or {}
    state["last_edit"] = {
        "ts": now if now is not None else time.time(),
        "file": path,
        "count": int(previous.get("count", 0)) + 1,
    }
    # New work means the previous round of nudging is spent.
    state["consecutive_blocks"] = 0
    save(state, event)
    return True


def touch_session(event=None, now=None):
    """Mark the start of a session, once.

    The filesystem scan needs a baseline: without one, every pre-existing file
    in the project looks like unverified work and a session that edited nothing
    would still be blocked. The first ratchet hook to see a new session id sets
    the mark; everything older than it is somebody else's problem.
    """
    session = (event or {}).get("session_id")
    state = load(event)
    if session and state.get("session_id") == session:
        return state
    state["session_id"] = session
    state["session_start"] = now if now is not None else time.time()
    state["consecutive_blocks"] = 0
    save(state, event)
    return state


def record_verification(command, exit_code, event=None, session=None, now=None):
    """Note a check that actually ran. Only a zero exit clears the gate."""
    state = load(event)
    state["last_verification"] = {
        "ts": now if now is not None else time.time(),
        "command": command,
        "exit": exit_code,
        "session": session,
    }
    if exit_code == 0:
        state["consecutive_blocks"] = 0
    save(state, event)
    return state


# Directories that never hold the user's code but can hold thousands of files.
PRUNE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "build", "dist", "target", ".gradle", ".idea", ".mypy_cache", ".pytest_cache",
    ".claude",
}

# A pathological repo should not make every Stop hook slow.
MAX_SCANNED_FILES = 20000


def _git_files(project):
    """Tracked plus untracked-but-not-ignored files, or None if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=project, capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _walked_files(project):
    """Fallback for non-git projects: a pruned, bounded walk."""
    found = []
    for root, dirs, files in os.walk(project):
        dirs[:] = [d for d in dirs if d not in PRUNE_DIRS and not d.startswith(".")]
        for name in files:
            found.append(os.path.relpath(os.path.join(root, name), project))
            if len(found) >= MAX_SCANNED_FILES:
                return found
    return found


def latest_code_change(event=None):
    """(mtime, path) of the most recently modified code file, or None.

    Reads the filesystem rather than trusting tool-call events, because the
    route a file was edited by is not something a gate can afford to care
    about. An edit made through Bash — `printf >> app.py`, `sed -i`, a heredoc —
    never fires a Write|Edit hook, so a gate driven only by those events is
    bypassed by the shell. This observes the result instead of the method.
    """
    project = hook_io.project_dir(event)
    names = _git_files(project)
    if names is None:
        names = _walked_files(project)

    newest = None
    for name in names[:MAX_SCANNED_FILES]:
        if not is_code(name):
            continue
        path = os.path.join(project, name)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if newest is None or mtime > newest[0]:
            newest = (mtime, name)
    return newest


def unverified(event=None):
    """(blocked, reason) — is there changed code with no newer passing check?

    The signal is the filesystem, not the tool log: an edit made through Bash
    never fires a Write|Edit hook, and a gate that can be stepped around by
    using a different tool is not a gate.
    """
    state = load(event)

    baseline = state.get("session_start")
    if baseline is None:
        # No ratchet hook has run yet this session, so there is no window in
        # which work could have happened. Nothing to judge.
        return False, None

    check = state.get("last_verification")
    verified_ts = None
    if isinstance(check, dict) and check.get("exit") == 0:
        try:
            verified_ts = float(check.get("ts", 0))
        except (TypeError, ValueError):
            return True, "the recorded verification has no usable timestamp."

    change = latest_code_change(event)
    if change is None:
        return False, None
    change_ts, changed_file = change

    # Only work done during this session counts.
    try:
        if change_ts <= float(baseline):
            return False, None
    except (TypeError, ValueError):
        return False, None

    if verified_ts is None:
        if isinstance(check, dict) and check.get("exit") not in (0, None):
            return True, (
                f"the last check (`{check.get('command')}`) exited "
                f"{check.get('exit')}."
            )
        return True, (
            f"{changed_file} changed this session, and no check has passed."
        )

    if verified_ts < change_ts:
        return True, (
            f"`{check.get('command')}` passed, but {changed_file} changed "
            "afterwards."
        )
    return False, None


def note_block(event=None):
    """Count a block, and report whether the gate should keep holding."""
    state = load(event)
    count = int(state.get("consecutive_blocks", 0)) + 1
    state["consecutive_blocks"] = count
    save(state, event)
    return count <= MAX_CONSECUTIVE_BLOCKS
