#!/usr/bin/env python3
"""Ratchet's session record: what Claude changed, and what was verified.

This is what lets a stateless hook answer "did this work get checked?". Every
hook appends events to one log per project, under ${CLAUDE_PLUGIN_DATA}:

    edit   a code file Claude wrote with Write, Edit or NotebookEdit
    shell  the time window of one of Claude's Bash or PowerShell calls
    check  a check command that ran, and its exit code
    block  the Stop hook refused to end a turn

At Stop, a code file counts as changed if Claude edited it this session, or if
its mtime falls inside one of this session's shell windows: an edit made with
`sed -i` or a script fires no Write|Edit hook, and a gate you can step around
by picking a different tool is not a gate. Files that changed some other way
(a clone, a checkout, a program, the user's editor) are not Claude's work and
do not count. That was most of the false alarms in 0.2.1, which judged every
file newer than the session start.

The latest check decides. If it passed after the newest change, the work is
verified; editing after a green run re-arms the gate, which is what makes this
a ratchet rather than a checkbox.

The log is append-only because hooks run concurrently: the shell logger is
async, and Claude often makes several tool calls at once. Read-modify-write on
one state file loses updates under that; appending a line does not.
"""

import json
import os
import re
import subprocess
import time

import hook_io

SCHEMA_VERSION = 2

# Editing prose or a config file Claude Code and git read should not demand a
# test run. Anything not excluded here counts as code, TOML, YAML, JSON and
# HTML included: erring toward "this needs verifying" is the safer default.
NON_CODE_SUFFIXES = {".md", ".txt", ".rst", ".adoc", ".log", ".example", ".session"}

# Extensionless files are code only when they are scripts (a shebang) or one
# of these. Extensionless config, such as OpenWrt's UCI files, is not.
BUILD_FILES = {"Makefile", "GNUmakefile", "Dockerfile", "Containerfile", "Jenkinsfile"}

# A Stop hook that cannot be satisfied traps the user in a loop. After this many
# consecutive blocks on the same batch of unverified edits, let the turn end.
MAX_CONSECUTIVE_BLOCKS = 2

# Seconds either side of a shell window, for mtime granularity and the gap
# between a command ending and its hook running.
WINDOW_SLACK = 1.0

# duration_ms is optional in the hook input. Without it, reach back as far as
# a foreground shell call can run: the Bash tool's maximum timeout.
MAX_SHELL_SECONDS = 600

# Other sessions' events older than this are dropped when the log is read.
PRUNE_AFTER_SECONDS = 24 * 3600

# Shell commands that rewrite the working tree from git rather than from
# Claude's hands. Files they produce are somebody else's code.
_GIT_TREE = re.compile(
    r"\bgit(?:\s+-[Cc]\s+\S+|\s+--?[\w-]+(?:=\S+)?)*\s+"
    r"(?:clone|checkout|switch|pull|merge|rebase|reset|stash|restore|"
    r"cherry-pick|revert|am|worktree|submodule)\b"
    r"|\bgh\s+repo\s+clone\b"
)

# Directories that never hold the user's code but can hold thousands of files.
PRUNE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "build", "dist", "target", ".gradle", ".idea", ".mypy_cache", ".pytest_cache",
    ".claude",
}

# A pathological repo should not make every Stop hook slow.
MAX_SCANNED_FILES = 20000


def is_code(path, root=None):
    """Whether a change to this path should arm the verification gate.

    `root` resolves a relative path for the one rule that reads the file: an
    extensionless file is code only if it starts with `#!`.
    """
    if not path:
        return False
    normalised = path.replace("\\", "/")
    # Ratchet's own and Claude Code's bookkeeping is not the user's work.
    if "/.claude/" in normalised or normalised.startswith(".claude/"):
        return False
    name = normalised.rsplit("/", 1)[-1]
    # .gitignore, .gitattributes, .env.example, .editorconfig: tool config.
    if name.startswith("."):
        return False
    suffix = os.path.splitext(name)[1].lower()
    if suffix:
        return suffix not in NON_CODE_SUFFIXES
    if name in BUILD_FILES:
        return True
    full = path if root is None or os.path.isabs(path) else os.path.join(root, path)
    try:
        with open(full, "rb") as handle:
            return handle.read(2) == b"#!"
    except OSError:
        return False


def _inside(path, project):
    project = os.path.normcase(os.path.abspath(project))
    path = os.path.normcase(os.path.abspath(path))
    return path == project or path.startswith(project.rstrip(os.sep) + os.sep)


def _append(kind, event, now=None, **fields):
    path = hook_io.event_log_path(event)
    if path is None:
        return False
    record = {
        "v": SCHEMA_VERSION,
        "ts": now if now is not None else time.time(),
        "session": (event or {}).get("session_id"),
        "kind": kind,
    }
    record.update(fields)
    hook_io.append_jsonl(path, record)
    return True


def record_edit(path, event=None, now=None):
    """Claude changed a file with a file tool. Re-arms the gate if it is code
    inside the project; scratch files elsewhere are not the user's work."""
    project = hook_io.project_dir(event)
    if not path or not _inside(path, project) or not is_code(path):
        return False
    return _append("edit", event, now, path=os.path.relpath(path, project))


def record_shell(command, event=None, now=None):
    """Claude ran a shell command. Files written during it are Claude's work,
    unless the command was git rewriting the working tree."""
    if not command or _GIT_TREE.search(command):
        return False
    end = now if now is not None else time.time()
    try:
        duration = float((event or {}).get("duration_ms")) / 1000.0
    except (TypeError, ValueError):
        duration = MAX_SHELL_SECONDS
    return _append("shell", event, end, start=end - max(duration, 0.0))


def record_check(command, exit_code, event=None, now=None):
    """A check ran. Only a zero exit clears the gate."""
    return _append("check", event, now, command=command, exit=exit_code)


def _session_events(event, now=None):
    """This session's events, oldest first. Prunes other sessions' stale ones."""
    path = hook_io.event_log_path(event)
    session = (event or {}).get("session_id")
    if path is None or not session:
        return []
    records = [record for record, ok in hook_io.read_jsonl(path) if ok]
    now = now if now is not None else time.time()
    keep = [
        r for r in records
        if r.get("session") == session or _ts(r) >= now - PRUNE_AFTER_SECONDS
    ]
    if len(keep) < len(records):
        _rewrite(path, keep)
    mine = [r for r in keep if r.get("session") == session]
    mine.sort(key=_ts)
    return mine


def _ts(record):
    try:
        return float(record.get("ts", 0))
    except (TypeError, ValueError):
        return 0.0


def _rewrite(path, records):
    """Best-effort: a prune that fails leaves the old log, which still works."""
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except OSError:
        pass


def _git_files(project):
    """Tracked plus untracked-but-not-ignored files, or None if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=project, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10,
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


def _shell_writes(project, windows, since):
    """(mtime, path) of code files whose mtime falls in one of the windows."""
    names = _git_files(project)
    if names is None:
        names = _walked_files(project)
    found = []
    for name in names[:MAX_SCANNED_FILES]:
        try:
            mtime = os.path.getmtime(os.path.join(project, name))
        except OSError:
            continue
        if since is not None and mtime <= since:
            continue
        if not any(start - WINDOW_SLACK <= mtime <= end + WINDOW_SLACK
                   for start, end in windows):
            continue
        if is_code(name, project):
            found.append((mtime, name.replace("\\", "/")))
    return found


def unverified(event=None, now=None):
    """(blocked, reason): did Claude change code with no newer passing check?"""
    events = _session_events(event, now)
    if not events:
        return False, None

    checks = [e for e in events if e.get("kind") == "check"]
    latest = checks[-1] if checks else None
    since = _ts(latest) if latest and latest.get("exit") == 0 else None

    changes = [
        (_ts(e), str(e.get("path", "")).replace("\\", "/"))
        for e in events
        if e.get("kind") == "edit" and (since is None or _ts(e) > since)
    ]
    windows = [
        (float(e.get("start", _ts(e))), _ts(e))
        for e in events
        if e.get("kind") == "shell" and (since is None or _ts(e) >= since - WINDOW_SLACK)
    ]
    if windows:
        changes.extend(_shell_writes(hook_io.project_dir(event), windows, since))
    if not changes:
        return False, None

    _, changed_file = max(changes)
    if latest is None:
        return True, f"{changed_file} changed this session, and no check has passed."
    if latest.get("exit") != 0:
        return True, (
            f"the last check (`{latest.get('command')}`) exited {latest.get('exit')}."
        )
    return True, (
        f"`{latest.get('command')}` passed, but {changed_file} changed afterwards."
    )


def note_block(event=None, now=None):
    """Count a block, and report whether the gate should keep holding.

    Blocks count since the latest edit or passing check: new work, or a green
    run, earns the gate its nudges back.
    """
    count = 0
    for record in reversed(_session_events(event, now)):
        kind = record.get("kind")
        if kind == "edit" or (kind == "check" and record.get("exit") == 0):
            break
        if kind == "block":
            count += 1
    _append("block", event, now)
    return count + 1 <= MAX_CONSECUTIVE_BLOCKS
