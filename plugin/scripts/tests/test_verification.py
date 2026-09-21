#!/usr/bin/env python3
"""Unit tests for the verification gate (session_state, verify_run, Stop hook).

The behaviour under test is a timestamp comparison: a verification counts only
if it is newer than the newest changed code file. Most of these tests pin the
edge cases where a gate would otherwise either trap the user or wave work
through.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.normpath(os.path.join(TEST_DIR, ".."))
sys.path.insert(0, SCRIPTS_DIR)

import session_state  # noqa: E402


class StateTestCase(unittest.TestCase):
    """Each test gets its own project dir, so state never leaks between them."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = self._tmp.name

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = self._saved
        self._tmp.cleanup()

    @property
    def project(self):
        return self._tmp.name

    def start_session(self, now=100.0):
        """Establish the baseline a real hook sets on its first fire."""
        session_state.touch_session({"session_id": "test"}, now=now)

    def touch_code(self, name="app.py", mtime=None):
        """Create or modify a file, optionally pinning its mtime."""
        path = os.path.join(self.project, name)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("x\n")
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path


class TestGateLogic(StateTestCase):
    def test_clean_session_is_not_blocked(self):
        self.start_session()
        blocked, _ = session_state.unverified()
        self.assertFalse(blocked)

    def test_preexisting_files_do_not_block(self):
        """A session that changed nothing must not be held for existing code."""
        self.touch_code(mtime=50.0)
        self.start_session(now=100.0)
        blocked, _ = session_state.unverified()
        self.assertFalse(blocked)

    def test_change_without_verification_blocks(self):
        self.start_session(now=100.0)
        self.touch_code(mtime=150.0)
        blocked, reason = session_state.unverified()
        self.assertTrue(blocked)
        self.assertIn("no check has passed", reason)

    def test_change_with_no_write_edit_event_still_blocks(self):
        """The hole this closes: a file changed via Bash fires no Write|Edit hook."""
        self.start_session(now=100.0)
        self.touch_code("touched_by_shell.py", mtime=150.0)
        self.assertIsNone(session_state.load().get("last_edit"))
        blocked, _ = session_state.unverified()
        self.assertTrue(blocked)

    def test_passing_check_after_change_clears(self):
        self.start_session(now=100.0)
        self.touch_code(mtime=150.0)
        session_state.record_verification("pytest", 0, now=160.0)
        blocked, _ = session_state.unverified()
        self.assertFalse(blocked)

    def test_change_after_passing_check_rearms(self):
        """The property that makes this a ratchet rather than a checkbox."""
        self.start_session(now=100.0)
        self.touch_code(mtime=150.0)
        session_state.record_verification("pytest", 0, now=160.0)
        self.touch_code(mtime=170.0)
        blocked, reason = session_state.unverified()
        self.assertTrue(blocked)
        self.assertIn("changed", reason)

    def test_failing_check_does_not_clear(self):
        self.start_session(now=100.0)
        self.touch_code(mtime=150.0)
        session_state.record_verification("pytest", 1, now=160.0)
        blocked, reason = session_state.unverified()
        self.assertTrue(blocked)
        self.assertIn("exited 1", reason)

    def test_no_baseline_means_nothing_to_judge(self):
        self.touch_code(mtime=150.0)
        blocked, _ = session_state.unverified()
        self.assertFalse(blocked)

    def test_prose_change_does_not_block(self):
        self.start_session(now=100.0)
        self.touch_code("NOTES.md", mtime=150.0)
        blocked, _ = session_state.unverified()
        self.assertFalse(blocked)


class TestEditClassification(StateTestCase):
    def test_prose_edits_do_not_arm_the_gate(self):
        self.assertFalse(session_state.record_edit("README.md"))
        self.assertFalse(session_state.record_edit("notes.txt"))

    def test_ratchet_own_state_does_not_arm_the_gate(self):
        self.assertFalse(
            session_state.record_edit(".claude/framework/session-state.json")
        )
        self.assertFalse(
            session_state.record_edit("/proj/.claude/PROJECT_PROFILE.md")
        )

    def test_code_edits_arm_the_gate(self):
        for path in ("a.py", "b.kt", "c.ts", "src/d.go", "Makefile"):
            with self.subTest(path=path):
                self.assertTrue(session_state.is_code(path))

    def test_windows_separators_are_handled(self):
        self.assertFalse(session_state.is_code(r"proj\.claude\thing.json"))
        self.assertTrue(session_state.is_code(r"proj\src\app.py"))


class TestBlockLimit(StateTestCase):
    def test_gate_gives_up_rather_than_trapping(self):
        """A Stop hook that cannot be satisfied is worse than one that yields."""
        self.start_session()
        self.assertTrue(session_state.note_block())   # 1st nudge
        self.assertTrue(session_state.note_block())   # 2nd nudge
        self.assertFalse(session_state.note_block())  # give up

    def test_new_edit_rearms_the_nudges(self):
        self.start_session()
        session_state.note_block()
        session_state.note_block()
        self.assertFalse(session_state.note_block())
        session_state.record_edit("src/app.py", now=200.0)
        self.assertTrue(session_state.note_block())

    def test_passing_check_resets_the_counter(self):
        self.start_session()
        session_state.note_block()
        session_state.record_verification("pytest", 0, now=101.0)
        self.assertEqual(session_state.load().get("consecutive_blocks"), 0)


class TestSessionBaseline(StateTestCase):
    def test_baseline_is_set_once_per_session(self):
        session_state.touch_session({"session_id": "a"}, now=100.0)
        session_state.touch_session({"session_id": "a"}, now=200.0)
        self.assertEqual(session_state.load()["session_start"], 100.0)

    def test_new_session_resets_the_baseline(self):
        session_state.touch_session({"session_id": "a"}, now=100.0)
        session_state.touch_session({"session_id": "b"}, now=200.0)
        self.assertEqual(session_state.load()["session_start"], 200.0)


class TestCorruptState(StateTestCase):
    def test_corrupt_state_file_degrades_to_empty(self):
        path = session_state.state_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        self.assertEqual(session_state.load(), {"version": 1})
        blocked, _ = session_state.unverified()
        self.assertFalse(blocked)

    def test_state_survives_a_write_after_corruption(self):
        path = session_state.state_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("[]")
        self.start_session(now=100.0)
        self.touch_code(mtime=150.0)
        blocked, _ = session_state.unverified()
        self.assertTrue(blocked)


def run_script(name, args=None, env=None, stdin=""):
    environment = dict(os.environ)
    if env:
        environment.update(env)
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS_DIR, name)] + (args or []),
        input=stdin,
        capture_output=True,
        text=True,
        env=environment,
    )


class TestVerifyRun(StateTestCase):
    # `exit N` is one of the few command forms cmd.exe and sh both honour.
    PASS = "exit 0"
    FAIL = "exit 3"

    def test_passing_command_records_a_receipt(self):
        proc = run_script(
            "verify_run.py",
            ["--command", self.PASS],
            env={"CLAUDE_PROJECT_DIR": self.project},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(session_state.load()["last_verification"]["exit"], 0)

    def test_failing_command_records_its_real_exit_code(self):
        """A pass cannot be asserted — only a real zero exit clears the gate."""
        self.start_session(now=100.0)
        self.touch_code(mtime=150.0)
        proc = run_script(
            "verify_run.py",
            ["--command", self.FAIL],
            env={"CLAUDE_PROJECT_DIR": self.project},
        )
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(session_state.load()["last_verification"]["exit"], 3)
        blocked, _ = session_state.unverified()
        self.assertTrue(blocked)

    def test_quoted_argument_is_not_resplit(self):
        """Regression: the command was once rejoined from argv, which dropped
        quoting and let the shell re-split it into separate commands."""
        marker = os.path.join(self.project, "marker.txt").replace("\\", "/")
        command = '{} -c "open(r\'{}\', \'w\').write(\'x\')"'.format(
            sys.executable, marker
        )
        proc = run_script(
            "verify_run.py",
            ["--command", command],
            env={"CLAUDE_PROJECT_DIR": self.project},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertTrue(os.path.isfile(marker), "quoted -c argument was mangled")
        self.assertEqual(
            session_state.load()["last_verification"]["command"], command
        )

    def test_unexpanded_session_placeholder_is_not_stored_literally(self):
        run_script(
            "verify_run.py",
            ["--session", "${CLAUDE_SESSION_ID}", "--command", self.PASS],
            env={"CLAUDE_PROJECT_DIR": self.project, "CLAUDE_SESSION_ID": ""},
        )
        self.assertIsNone(session_state.load()["last_verification"]["session"])

    def test_no_command_is_an_error(self):
        for args in ([], ["--command", "   "]):
            with self.subTest(args=args):
                proc = run_script(
                    "verify_run.py", args,
                    env={"CLAUDE_PROJECT_DIR": self.project},
                )
                self.assertEqual(proc.returncode, 2)


class TestStopHook(StateTestCase):
    def _run(self, event=None):
        return run_script(
            "require_verification.py",
            env={"CLAUDE_PROJECT_DIR": self.project},
            stdin=json.dumps(event or {}),
        )

    def test_blocks_on_unverified_changes(self):
        self.start_session(now=100.0)
        self.touch_code(mtime=150.0)
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        # Top-level, not nested under hookSpecificOutput: the nested shape is
        # PreToolUse's, and Claude Code ignores it on Stop. A hook that emits it
        # looks like it works and blocks nothing.
        self.assertNotIn("hookSpecificOutput", payload)
        self.assertEqual(payload["decision"], "block")
        reason = payload["reason"].lower()
        self.assertIn("without a passing check", reason)
        self.assertIn("no check has passed", reason)

    def test_silent_when_nothing_changed(self):
        self.start_session(now=100.0)
        self.assertEqual(self._run().stdout.strip(), "")

    def test_silent_after_a_passing_check(self):
        self.start_session(now=100.0)
        self.touch_code(mtime=150.0)
        session_state.record_verification("pytest", 0, now=160.0)
        self.assertEqual(self._run().stdout.strip(), "")

    def test_respects_stop_hook_active(self):
        self.start_session(now=100.0)
        self.touch_code(mtime=150.0)
        proc = self._run({"stop_hook_active": True})
        self.assertEqual(proc.stdout.strip(), "")

    def test_gives_up_after_repeated_blocks(self):
        self.start_session(now=100.0)
        self.touch_code(mtime=150.0)
        self.assertIn("block", self._run().stdout)
        self.assertIn("block", self._run().stdout)
        final = self._run().stdout
        self.assertNotIn('"decision"', final)
        self.assertIn("letting this turn end", final)

    def test_exits_zero_on_garbage_input(self):
        proc = run_script(
            "require_verification.py",
            env={"CLAUDE_PROJECT_DIR": self.project},
            stdin="not json",
        )
        self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
