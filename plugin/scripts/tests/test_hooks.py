#!/usr/bin/env python3
"""Unit tests for ratchet's hook scripts.

These cover the script logic directly. The eval suite in plugin/evals/ grades
model *behaviour* and cannot catch a hook that mangles its own input — which is
how the two bugs these tests pin down shipped in the first place.
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.normpath(os.path.join(TEST_DIR, ".."))
PLUGIN_DIR = os.path.normpath(os.path.join(SCRIPTS_DIR, ".."))
FIXTURES_DIR = os.path.join(TEST_DIR, "fixtures")
sys.path.insert(0, SCRIPTS_DIR)

import check_file_size  # noqa: E402
import hook_io  # noqa: E402


def run_hook(script_name, event=None, env=None, cwd=None, raw=None):
    """Run a hook end to end the way Claude Code does: JSON on stdin.

    Always hands the hook throwaway project and plugin-data dirs unless the
    caller names them, so a test run never writes into the source tree or into
    the real ~/.claude/plugins/data.
    """
    environment = dict(os.environ)
    environment.pop("CLAUDE_PLUGIN_ROOT", None)
    # As ratchet-hook.sh does: no __pycache__/ in plugin/, which gets installed.
    environment["PYTHONDONTWRITEBYTECODE"] = "1"

    scratch = []
    for key in ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_DATA"):
        if not (env or {}).get(key):
            scratch.append(tempfile.TemporaryDirectory())
            environment[key] = scratch[-1].name
    if env:
        environment.update(env)

    try:
        return subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, script_name)],
            input=raw if raw is not None else json.dumps(event or {}),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            cwd=cwd,
        )
    finally:
        for directory in scratch:
            directory.cleanup()


class TestEventParsing(unittest.TestCase):
    """The regression tests for bug 2: the `[^"]*` fallback extractor."""

    def _parse(self, raw):
        original = sys.stdin
        sys.stdin = io.StringIO(raw)
        try:
            return hook_io.read_event()
        finally:
            sys.stdin = original

    def test_command_with_embedded_quotes_survives(self):
        """The exact shape that produced `{"cmd":"cd \\\\"}` in the real log.

        The old extractor stopped at the first escaped quote, truncating the
        command mid-escape. The truncated line was still valid JSON, so
        find-patterns counted it as a real command.
        """
        command = 'cd "C:/Program Files/x" && ls'
        raw = json.dumps({"tool_input": {"command": command}})
        event = self._parse(raw)
        self.assertEqual(hook_io.tool_input(event, "command"), command)

    def test_command_with_backslashes_and_quotes(self):
        command = 'grep -o \'"command"\\s*:\\s*"[^"]*"\' file.json'
        raw = json.dumps({"tool_input": {"command": command}})
        self.assertEqual(
            hook_io.tool_input(self._parse(raw), "command"), command
        )

    def test_empty_stdin_yields_empty_event(self):
        self.assertEqual(self._parse(""), {})

    def test_malformed_json_yields_empty_event(self):
        self.assertEqual(self._parse("{not json"), {})

    def test_non_object_json_yields_empty_event(self):
        self.assertEqual(self._parse("[1, 2, 3]"), {})

    def test_missing_tool_input_returns_default(self):
        self.assertIsNone(hook_io.tool_input({}, "command"))
        self.assertIsNone(hook_io.tool_input({"tool_input": "nope"}, "command"))


class TestProjectDirAnchoring(unittest.TestCase):
    """The regression tests for bug 1: the unanchored relative path."""

    def setUp(self):
        self._saved = {
            key: os.environ.pop(key, None)
            for key in ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT",
                        "CLAUDE_PLUGIN_DATA")
        }

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_env_var_wins(self):
        os.environ["CLAUDE_PROJECT_DIR"] = os.path.join("X:", "anchored")
        self.assertEqual(
            hook_io.project_dir({"cwd": "/somewhere/else"}),
            os.path.join("X:", "anchored"),
        )

    def test_falls_back_to_event_cwd(self):
        self.assertEqual(
            hook_io.project_dir({"cwd": "/from/event"}), "/from/event"
        )

    def test_data_dir_comes_from_the_environment(self):
        self.assertIsNone(hook_io.data_dir())
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CLAUDE_PLUGIN_DATA"] = tmp
            try:
                self.assertEqual(hook_io.data_dir(), tmp)
            finally:
                os.environ.pop("CLAUDE_PLUGIN_DATA")


class TestLogToolCall(unittest.TestCase):
    def setUp(self):
        self._project = tempfile.TemporaryDirectory()
        self._data = tempfile.TemporaryDirectory()
        self.env = {"CLAUDE_PROJECT_DIR": self._project.name,
                    "CLAUDE_PLUGIN_DATA": self._data.name}
        self.log = os.path.join(self._data.name, "tool-log.jsonl")

    def tearDown(self):
        self._project.cleanup()
        self._data.cleanup()

    def entries(self):
        return hook_io.read_jsonl(self.log)

    def test_quoted_command_round_trips_through_the_log(self):
        """End to end: the log must read back byte-identical to what went in."""
        command = 'cd "C:/Program Files/x" && echo "done"'
        run_hook("log_tool_call.py", {"tool_input": {"command": command}},
                 env=self.env)
        self.assertTrue(os.path.isfile(self.log), "hook wrote no log")
        entries = self.entries()
        self.assertEqual(len(entries), 1)
        record, ok = entries[0]
        self.assertTrue(ok, f"log line did not parse: {record!r}")
        self.assertEqual(record["cmd"], command)
        self.assertEqual(record["project"], self._project.name)

    def test_log_is_written_under_plugin_data_only(self):
        """Neither the shell's cwd nor the project gets a stray .claude tree."""
        with tempfile.TemporaryDirectory() as elsewhere:
            run_hook("log_tool_call.py", {"tool_input": {"command": "ls"}},
                     env=self.env, cwd=elsewhere)
            self.assertTrue(os.path.isfile(self.log))
            self.assertEqual(os.listdir(elsewhere), [])
        self.assertEqual(os.listdir(self._project.name), [])

    def test_long_command_is_truncated(self):
        run_hook("log_tool_call.py", {"tool_input": {"command": "x" * 500}},
                 env=self.env)
        record, _ = self.entries()[0]
        self.assertEqual(len(record["cmd"]), 120)

    def test_no_command_writes_no_log_entry(self):
        run_hook("log_tool_call.py", {"tool_input": {"file_path": "a.txt"}},
                 env=self.env)
        self.assertFalse(os.path.exists(self.log))

    def test_hook_exits_zero_on_garbage_input(self):
        proc = run_hook("log_tool_call.py", raw="not json at all")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_powershell_command_is_logged(self):
        """The PowerShell tool sends the same `command` field as Bash."""
        run_hook("log_tool_call.py",
                 {"tool_name": "PowerShell",
                  "tool_input": {"command": "Get-ChildItem -LiteralPath $p"}},
                 env=self.env)
        record, ok = self.entries()[0]
        self.assertTrue(ok)
        self.assertEqual(record["cmd"], "Get-ChildItem -LiteralPath $p")

    def test_failed_command_is_logged_too(self):
        run_hook("log_tool_call.py",
                 {"hook_event_name": "PostToolUseFailure",
                  "tool_input": {"command": "false"}, "error": "Exit code 1"},
                 env=self.env)
        record, _ = self.entries()[0]
        self.assertEqual(record["cmd"], "false")

    def test_without_plugin_data_nothing_is_written(self):
        run_hook("log_tool_call.py", {"tool_input": {"command": "ls"}},
                 env={"CLAUDE_PROJECT_DIR": self._project.name,
                      "CLAUDE_PLUGIN_DATA": ""})
        self.assertEqual(os.listdir(self._project.name), [])


class TestReadJsonl(unittest.TestCase):
    def test_malformed_lines_are_flagged_not_dropped(self):
        """Provenance: a reader must be able to say how much it could not parse.

        The corrupt lines in the real log were valid JSON, so this also covers
        the subtler case — a line that parses but is not an object.
        """
        path = os.path.join(FIXTURES_DIR, "log_mixed.jsonl")
        entries = hook_io.read_jsonl(path)
        good = [record for record, ok in entries if ok]
        bad = [record for record, ok in entries if not ok]
        self.assertEqual(len(good), 2)
        self.assertEqual(len(bad), 2)

    def test_empty_log(self):
        self.assertEqual(
            hook_io.read_jsonl(os.path.join(FIXTURES_DIR, "log_empty.jsonl")), []
        )

    def test_truncated_final_line(self):
        entries = hook_io.read_jsonl(
            os.path.join(FIXTURES_DIR, "log_truncated.jsonl")
        )
        self.assertEqual(len([r for r, ok in entries if ok]), 1)
        self.assertEqual(len([r for r, ok in entries if not ok]), 1)

    def test_missing_file_is_not_an_error(self):
        self.assertEqual(hook_io.read_jsonl("/no/such/log.jsonl"), [])


class TestCheckFileSize(unittest.TestCase):
    def test_threshold_default_and_override(self):
        os.environ.pop("RATCHET_FILE_SIZE_THRESHOLD", None)
        self.assertEqual(check_file_size.threshold(), 400)
        try:
            os.environ["RATCHET_FILE_SIZE_THRESHOLD"] = "10"
            self.assertEqual(check_file_size.threshold(), 10)
            os.environ["RATCHET_FILE_SIZE_THRESHOLD"] = "banana"
            self.assertEqual(check_file_size.threshold(), 400)
            os.environ["RATCHET_FILE_SIZE_THRESHOLD"] = "0"
            self.assertEqual(check_file_size.threshold(), 400)
        finally:
            os.environ.pop("RATCHET_FILE_SIZE_THRESHOLD", None)

    def test_warns_only_over_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            big = os.path.join(tmp, "big.py")
            with open(big, "w", encoding="utf-8") as handle:
                handle.write("x\n" * 50)

            over = run_hook(
                "check_file_size.py",
                {"tool_input": {"file_path": big}},
                env={"RATCHET_FILE_SIZE_THRESHOLD": "10"},
            )
            self.assertIn("50 lines", over.stdout)

            under = run_hook(
                "check_file_size.py",
                {"tool_input": {"file_path": big}},
                env={"RATCHET_FILE_SIZE_THRESHOLD": "100"},
            )
            self.assertEqual(under.stdout.strip(), "")

    def test_missing_file_is_silent(self):
        proc = run_hook(
            "check_file_size.py", {"tool_input": {"file_path": "/no/such/file"}}
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")

    def test_path_with_spaces_and_metacharacters(self):
        """A filename that naive shell handling would split or expand.

        NTFS forbids `"` in a filename, so the quote case cannot be exercised
        here — spaces, `&` and `$` are the legal characters that still break an
        unquoted shell expansion.
        """
        with tempfile.TemporaryDirectory() as tmp:
            odd = os.path.join(tmp, "a name & $with meta.py")
            with open(odd, "w", encoding="utf-8") as handle:
                handle.write("x\n" * 50)
            proc = run_hook(
                "check_file_size.py",
                {"tool_input": {"file_path": odd}},
                env={"RATCHET_FILE_SIZE_THRESHOLD": "10"},
            )
            self.assertIn("50 lines", proc.stdout)


class TestHooksManifest(unittest.TestCase):
    """hooks.json fails silently: a matcher that misses a tool never fires."""

    def _manifest(self):
        path = os.path.join(PLUGIN_DIR, "hooks", "hooks.json")
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _entries(self, event_name, script_name):
        """(matcher, hook) for each hooks.json entry running a script."""
        return [
            (group.get("matcher", ""), hook)
            for group in self._manifest()["hooks"].get(event_name, [])
            for hook in group.get("hooks", [])
            if script_name in hook.get("command", "")
        ]

    def _only(self, event_name, script_name):
        found = self._entries(event_name, script_name)
        self.assertEqual(len(found), 1, f"{script_name} under {event_name}")
        return found[0]

    def test_logger_hears_bash_and_powershell_success_and_failure(self):
        """A `Bash`-only matcher never fires for the PowerShell tool, and a
        failing check only ever reaches PostToolUseFailure."""
        for event_name in ("PostToolUse", "PostToolUseFailure"):
            matcher, _ = self._only(event_name, "log_tool_call.py")
            for tool in ("Bash", "PowerShell"):
                with self.subTest(event=event_name, tool=tool):
                    self.assertTrue(re.fullmatch(matcher, tool),
                                    f"logger matcher {matcher!r} misses {tool}")

    def test_edit_recorder_hears_every_file_tool(self):
        matcher, _ = self._only("PostToolUse", "check_file_size.py")
        for tool in ("Write", "Edit", "NotebookEdit"):
            with self.subTest(tool=tool):
                self.assertTrue(re.fullmatch(matcher, tool))

    def test_every_hook_is_handed_the_plugin_data_dir(self):
        """Claude Code exports CLAUDE_PLUGIN_DATA to hooks only once a hook
        command references it (seen in 2.1.296 eval runs). Without it the gate
        has nowhere to keep state and switches itself off."""
        for event_name, groups in self._manifest()["hooks"].items():
            for group in groups:
                for hook in group["hooks"]:
                    with self.subTest(event=event_name, command=hook["command"]):
                        self.assertIn('CLAUDE_PLUGIN_DATA="${CLAUDE_PLUGIN_DATA}"',
                                      hook["command"])

    def test_logger_runs_async(self):
        """The logger only records; no tool call should wait on it."""
        for event_name in ("PostToolUse", "PostToolUseFailure"):
            _, hook = self._only(event_name, "log_tool_call.py")
            self.assertIs(hook.get("async"), True, event_name)

    def test_steering_hooks_stay_synchronous(self):
        """The size warning and the Stop gate talk back to Claude. An async
        hook cannot block, and what it says arrives after Claude moved on."""
        for event_name, script in (
            ("PostToolUse", "check_file_size.py"),
            ("Stop", "require_verification.py"),
        ):
            _, hook = self._only(event_name, script)
            self.assertFalse(hook.get("async", False), script)


class TestNotebookEdit(unittest.TestCase):
    def test_notebook_edit_arms_the_gate(self):
        with tempfile.TemporaryDirectory() as project,                 tempfile.TemporaryDirectory() as data:
            notebook = os.path.join(project, "analysis.ipynb")
            with open(notebook, "w", encoding="utf-8") as handle:
                handle.write("{}")
            env = {"CLAUDE_PROJECT_DIR": project, "CLAUDE_PLUGIN_DATA": data}
            run_hook("check_file_size.py",
                     {"session_id": "s1", "tool_name": "NotebookEdit",
                      "tool_input": {"notebook_path": notebook}}, env=env)
            stop = run_hook("require_verification.py", {"session_id": "s1"},
                            env=env)
            self.assertIn('"decision"', stop.stdout)
            self.assertIn("analysis.ipynb", stop.stdout)


@unittest.skipIf(shutil.which("git") is None, "git not on PATH")
class TestHooksLeaveTheProjectAlone(unittest.TestCase):
    """0.2.1 kept its state in `<project>/.claude/framework/`. Now that state
    lives under the plugin's data dir, git must see no new files at all, with
    no ignore file anywhere to hide them.

    Git runs with an empty global config and no system config, so a personal
    excludes file cannot make this pass by accident.
    """

    def test_git_status_is_clean_after_every_hook_ran(self):
        with tempfile.TemporaryDirectory() as project,                 tempfile.TemporaryDirectory() as data:
            empty = os.path.join(data, "empty.gitconfig")
            open(empty, "w").close()
            git_env = dict(os.environ, GIT_CONFIG_GLOBAL=empty,
                           GIT_CONFIG_NOSYSTEM="1")

            def git(*args):
                return subprocess.run(["git", *args], cwd=project, env=git_env,
                                      capture_output=True, text=True)

            self.assertEqual(git("init", "-q").returncode, 0)
            code = os.path.join(project, "app.py")
            open(code, "w").close()
            git("add", "-A")
            git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "i")

            env = {"CLAUDE_PROJECT_DIR": project, "CLAUDE_PLUGIN_DATA": data}
            for script, event in (
                ("log_tool_call.py", {"tool_input": {"command": "ls"}}),
                ("check_file_size.py", {"tool_name": "Edit",
                                        "tool_input": {"file_path": code}}),
                ("require_verification.py", {}),
            ):
                event = dict(event, session_id="s1")
                proc = run_hook(script, event, env=env)
                self.assertEqual(proc.returncode, 0, proc.stderr)

            status = git("status", "--porcelain", "--untracked-files=all",
                         "--ignored").stdout
            self.assertEqual(status, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
