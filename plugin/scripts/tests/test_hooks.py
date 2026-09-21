#!/usr/bin/env python3
"""Unit tests for ratchet's hook scripts.

These cover the script logic directly. The eval suite in plugin/evals/ grades
model *behaviour* and cannot catch a hook that mangles its own input — which is
how the two bugs these tests pin down shipped in the first place.
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.normpath(os.path.join(TEST_DIR, ".."))
FIXTURES_DIR = os.path.join(TEST_DIR, "fixtures")
sys.path.insert(0, SCRIPTS_DIR)

import check_file_size  # noqa: E402
import hook_io  # noqa: E402


def run_hook(script_name, event, env=None, cwd=None):
    """Run a hook end to end the way Claude Code does: JSON on stdin."""
    environment = dict(os.environ)
    environment.pop("CLAUDE_PROJECT_DIR", None)
    environment.pop("CLAUDE_PLUGIN_ROOT", None)
    if env:
        environment.update(env)
    proc = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS_DIR, script_name)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=environment,
        cwd=cwd,
    )
    return proc


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
            for key in ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT")
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

    def test_framework_dir_is_under_project_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CLAUDE_PROJECT_DIR"] = tmp
            self.assertEqual(
                hook_io.framework_dir(),
                os.path.join(tmp, ".claude", "framework"),
            )


class TestLogToolCall(unittest.TestCase):
    def test_quoted_command_round_trips_through_the_log(self):
        """End to end: the log must read back byte-identical to what went in."""
        command = 'cd "C:/Program Files/x" && echo "done"'
        with tempfile.TemporaryDirectory() as tmp:
            run_hook(
                "log_tool_call.py",
                {"tool_input": {"command": command}},
                env={"CLAUDE_PROJECT_DIR": tmp},
            )
            log = os.path.join(tmp, ".claude", "framework", "tool-log.jsonl")
            self.assertTrue(os.path.isfile(log), "hook wrote no log")
            entries = hook_io.read_jsonl(log)
            self.assertEqual(len(entries), 1)
            record, ok = entries[0]
            self.assertTrue(ok, f"log line did not parse: {record!r}")
            self.assertEqual(record["cmd"], command)

    def test_log_is_written_under_project_dir_not_cwd(self):
        """Bug 1: the hook must not write into whatever directory it runs in."""
        with tempfile.TemporaryDirectory() as project, \
                tempfile.TemporaryDirectory() as elsewhere:
            run_hook(
                "log_tool_call.py",
                {"tool_input": {"command": "ls"}},
                env={"CLAUDE_PROJECT_DIR": project},
                cwd=elsewhere,
            )
            self.assertTrue(
                os.path.isfile(
                    os.path.join(project, ".claude", "framework", "tool-log.jsonl")
                )
            )
            self.assertFalse(
                os.path.exists(os.path.join(elsewhere, ".claude")),
                "hook wrote a stray .claude tree into its working directory",
            )

    def test_long_command_is_truncated(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_hook(
                "log_tool_call.py",
                {"tool_input": {"command": "x" * 500}},
                env={"CLAUDE_PROJECT_DIR": tmp},
            )
            log = os.path.join(tmp, ".claude", "framework", "tool-log.jsonl")
            record, _ = hook_io.read_jsonl(log)[0]
            self.assertEqual(len(record["cmd"]), 120)

    def test_no_command_writes_no_log_entry(self):
        """An event with no command logs nothing.

        The session-state file may still appear: the hook marks the session
        baseline before it looks for a command, which is deliberate.
        """
        with tempfile.TemporaryDirectory() as tmp:
            run_hook(
                "log_tool_call.py",
                {"tool_input": {"file_path": "a.txt"}},
                env={"CLAUDE_PROJECT_DIR": tmp},
            )
            log = os.path.join(tmp, ".claude", "framework", "tool-log.jsonl")
            self.assertFalse(os.path.exists(log))

    def test_hook_exits_zero_on_garbage_input(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "log_tool_call.py")],
            input="not json at all",
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
