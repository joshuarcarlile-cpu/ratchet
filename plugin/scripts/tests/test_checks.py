#!/usr/bin/env python3
"""Unit tests for recognising a check run in a Bash or PowerShell call.

A pass is recorded only when the shell call's exit status is the check's own.
`check | tail`, `check; echo done` and `check || true` all report success
whatever the check did, so they must never clear the gate. The commands below
are shaped like ones in the audited transcripts.
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

import checks  # noqa: E402
import session_state  # noqa: E402

FULL, PASS_ONLY = checks.FULL, checks.PASS_ONLY

PROFILE = """# Project Profile

## Commands
- Test: `{test}`{tail}
- Lint/build: `make lint`
"""


def write_profile(project, test, tail=""):
    os.makedirs(os.path.join(project, ".claude"), exist_ok=True)
    with open(os.path.join(project, ".claude", "PROJECT_PROFILE.md"), "w",
              encoding="utf-8") as handle:
        handle.write(PROFILE.format(test=test, tail=tail))


class TestProfiledCheck(unittest.TestCase):
    def test_first_backticked_command_on_the_test_line(self):
        with tempfile.TemporaryDirectory() as project:
            write_profile(project, r".\gradlew.bat testDebugUnitTest assembleDebug",
                          " (run via `verify_run.py` as `cd /d <project> && x`)")
            self.assertEqual(checks.profiled_check(project),
                             r".\gradlew.bat testDebugUnitTest assembleDebug")

    def test_no_command_recorded(self):
        with tempfile.TemporaryDirectory() as project:
            os.makedirs(os.path.join(project, ".claude"))
            with open(os.path.join(project, ".claude", "PROJECT_PROFILE.md"), "w",
                      encoding="utf-8") as handle:
                handle.write("## Commands\n- Test: none. No test suite exists.\n")
            self.assertIsNone(checks.profiled_check(project))

    def test_missing_profile(self):
        with tempfile.TemporaryDirectory() as project:
            self.assertIsNone(checks.profiled_check(project))


class TestAttribution(unittest.TestCase):
    CHECK = 'py -3 -m unittest discover -s plugin/scripts/tests -p "test_*.py"'

    def assertAttribution(self, command, expected, check=None):
        self.assertEqual(
            checks.attribution(command, check or self.CHECK), expected, command
        )

    def test_the_check_alone(self):
        self.assertAttribution(self.CHECK, FULL)

    def test_setup_before_the_check_is_fine(self):
        self.assertAttribution("cd /c/Users/joshu/Projects/ratchet && " + self.CHECK, FULL)
        self.assertAttribution("PYTHONDONTWRITEBYTECODE=1 " + self.CHECK, FULL)
        self.assertAttribution("cd /c/x\n" + self.CHECK, FULL)
        self.assertAttribution("$env:PYTHONDONTWRITEBYTECODE=1; " + self.CHECK, FULL)

    def test_redirections_keep_the_exit_status(self):
        self.assertAttribution(self.CHECK + " 2>&1", FULL)
        self.assertAttribution(self.CHECK + " > out.txt 2>&1", FULL)
        self.assertAttribution(self.CHECK + " 2>$null", FULL)

    def test_anything_after_the_check_hides_its_exit_status(self):
        for tail in (" | tail -5", " 2>&1 | grep -E 'FAIL|OK'", "; echo done",
                     " || true", " &", "\necho done",
                     ' | Select-String -Pattern "FAILED"'):
            with self.subTest(tail=tail):
                self.assertAttribution(self.CHECK + tail, None)

    def test_and_then_counts_for_a_pass_only(self):
        """`check && git commit` succeeding means the check passed; failing
        could be the commit, so it says nothing about the check."""
        self.assertAttribution(self.CHECK + " && git commit -qm x", PASS_ONLY)

    def test_check_behind_or_does_not_count(self):
        self.assertAttribution("true || " + self.CHECK, None)

    def test_the_check_must_be_the_command_not_an_argument(self):
        self.assertAttribution("echo " + self.CHECK, None)
        self.assertAttribution('echo "' + self.CHECK + '"', None)
        self.assertAttribution("x" + self.CHECK, None)

    def test_extra_arguments_are_a_different_check(self):
        """A subset of the suite is not the suite."""
        self.assertAttribution(self.CHECK + " -k slow", None)

    def test_shell_spellings_of_the_same_command(self):
        check = r".\gradlew.bat testDebugUnitTest assembleDebug"
        self.assertAttribution("./gradlew.bat testDebugUnitTest assembleDebug", FULL, check)
        self.assertAttribution(r".\gradlew.bat  testDebugUnitTest assembleDebug", FULL, check)
        self.assertAttribution(r"& .\gradlew.bat testDebugUnitTest assembleDebug", FULL, check)
        self.assertAttribution(
            r"cd /d C:\Users\joshu\chan && .\gradlew.bat testDebugUnitTest assembleDebug",
            FULL, check)

    def test_the_audited_piped_gradle_run_does_not_count(self):
        """SettingsNavigationTest.kt: the run after the edit was piped."""
        check = r".\gradlew.bat testDebugUnitTest assembleDebug"
        self.assertAttribution(
            r'.\gradlew.bat testDebugUnitTest assembleDebug --console=plain 2>&1 | '
            r'Select-String -Pattern "^e: |FAILED|BUILD" | Select-Object -First 30',
            None, check)

    def test_operators_inside_quotes_do_not_split(self):
        check = 'bash -c "a && b | c"'
        self.assertAttribution(check, FULL, check)


class TestVerifyRunInvocation(unittest.TestCase):
    PREFIX = ('CLAUDE_PROJECT_DIR="C:/dev/network-stuff" '
              '"C:/Users/joshu/.claude/plugins/cache/ratchet-marketplace/ratchet/0.2.1/'
              'bin/ratchet-hook.sh" verify_run.py --session "abc" ')

    def test_inner_command_is_the_check(self):
        command = self.PREFIX + '--command "bash -n scripts/server/router_probes.sh"'
        self.assertEqual(checks.verify_run_target(command),
                         ("bash -n scripts/server/router_probes.sh", FULL))

    def test_quoted_operators_and_backslashes_survive(self):
        command = (self.PREFIX + r'--command "cd /d C:\Users\joshu\chan && '
                   r'.\gradlew.bat testDebugUnitTest"')
        self.assertEqual(
            checks.verify_run_target(command),
            (r"cd /d C:\Users\joshu\chan && .\gradlew.bat testDebugUnitTest", FULL))

    def test_piped_runner_does_not_count(self):
        command = self.PREFIX + '--command "bash -n a.sh" | tail -3'
        self.assertIsNone(checks.verify_run_target(command))

    def test_not_a_runner_invocation(self):
        self.assertIsNone(checks.verify_run_target("cat plugin/scripts/verify_run.py"))
        self.assertIsNone(checks.verify_run_target("grep -n main verify_run.py"))


class TestResult(unittest.TestCase):
    CHECK = "pytest -q"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = self._tmp.name
        write_profile(self.project, self.CHECK)

    def tearDown(self):
        self._tmp.cleanup()

    def event(self, command, failed=False, **extra):
        event = {
            "hook_event_name": "PostToolUseFailure" if failed else "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
        }
        if failed:
            event["error"] = "Exit code 3\nFAILED test_x"
        else:
            event["tool_response"] = {"stdout": "", "stderr": "", "interrupted": False}
        event.update(extra)
        return event

    def result(self, event):
        return checks.result(event, self.project)

    def test_success_is_a_pass(self):
        self.assertEqual(self.result(self.event(self.CHECK)), (self.CHECK, 0))

    def test_failure_records_the_exit_code(self):
        self.assertEqual(self.result(self.event(self.CHECK, failed=True)),
                         (self.CHECK, 3))

    def test_failure_of_an_and_then_chain_says_nothing(self):
        self.assertIsNone(self.result(self.event(self.CHECK + " && git push", failed=True)))

    def test_failure_without_an_exit_code_says_nothing(self):
        event = self.event(self.CHECK, failed=True, error="could not start shell")
        self.assertIsNone(self.result(event))

    def test_interrupted_or_background_is_not_a_pass(self):
        interrupted = self.event(self.CHECK)
        interrupted["tool_response"]["interrupted"] = True
        self.assertIsNone(self.result(interrupted))
        background = self.event(self.CHECK)
        background["tool_input"]["run_in_background"] = True
        self.assertIsNone(self.result(background))

    def test_unrelated_command_is_not_a_check(self):
        self.assertIsNone(self.result(self.event("git status")))

    def test_runner_invocation_is_a_check_without_a_profile(self):
        os.remove(os.path.join(self.project, ".claude", "PROJECT_PROFILE.md"))
        command = '"/x/bin/ratchet-hook.sh" verify_run.py --command "bash -n a.sh"'
        self.assertEqual(self.result(self.event(command)), ("bash -n a.sh", 0))

    def test_powershell_tool(self):
        event = self.event(self.CHECK, tool_name="PowerShell")
        self.assertEqual(self.result(event), (self.CHECK, 0))


class TestLoggerRecordsChecks(unittest.TestCase):
    """End to end through log_tool_call.py, the way Claude Code calls it."""

    CHECK = "pytest -q"

    def setUp(self):
        self._project = tempfile.TemporaryDirectory()
        self._data = tempfile.TemporaryDirectory()
        self.project, self.data = self._project.name, self._data.name
        write_profile(self.project, self.CHECK)
        self.env = dict(os.environ, CLAUDE_PROJECT_DIR=self.project,
                        CLAUDE_PLUGIN_DATA=self.data, PYTHONDONTWRITEBYTECODE="1")
        self._saved = {k: os.environ.get(k)
                       for k in ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_DATA")}
        os.environ.update(CLAUDE_PROJECT_DIR=self.project, CLAUDE_PLUGIN_DATA=self.data)

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._project.cleanup()
        self._data.cleanup()

    def hook(self, script, event):
        event = dict(event, session_id="s1", cwd=self.project)
        return subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, script)],
            input=json.dumps(event), capture_output=True, text=True,
            encoding="utf-8", env=self.env,
        )

    def edit(self):
        path = os.path.join(self.project, "app.py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("x = 1\n")
        self.hook("check_file_size.py",
                  {"tool_name": "Edit", "tool_input": {"file_path": path}})

    def shell(self, command, failed=False):
        event = {"hook_event_name": "PostToolUseFailure" if failed else "PostToolUse",
                 "tool_name": "Bash", "tool_input": {"command": command},
                 "duration_ms": 50}
        if failed:
            event["error"] = "Exit code 1\nboom"
        else:
            event["tool_response"] = {"interrupted": False}
        return self.hook("log_tool_call.py", event)

    def blocked(self):
        return session_state.unverified({"session_id": "s1", "cwd": self.project})[0]

    def test_running_the_profiled_check_clears_the_gate(self):
        self.edit()
        self.assertTrue(self.blocked())
        proc = self.shell(self.CHECK)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(self.blocked())

    def test_piped_check_does_not_clear_the_gate(self):
        self.edit()
        self.shell(self.CHECK + " 2>&1 | tail -5")
        self.assertTrue(self.blocked())

    def test_failing_check_keeps_the_gate_armed(self):
        self.edit()
        self.shell(self.CHECK)
        self.shell(self.CHECK, failed=True)
        self.assertTrue(self.blocked())


if __name__ == "__main__":
    unittest.main(verbosity=2)
