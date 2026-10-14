#!/usr/bin/env python3
"""Unit tests for the verification gate (session_state, verify_run, Stop hook).

The gate compares two things from one session: the newest code change Claude
made, and the newest check that ran. Most of these tests pin the edge cases
where a gate would otherwise either trap the user or wave work through. The
false alarms the 13 Oct 2026 audit measured each have a test here.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.normpath(os.path.join(TEST_DIR, ".."))
sys.path.insert(0, SCRIPTS_DIR)

import hook_io  # noqa: E402
import session_state  # noqa: E402

SESSION = "s1"


class StateTestCase(unittest.TestCase):
    """Each test gets its own project and plugin-data dirs, so nothing leaks."""

    def setUp(self):
        self._project = tempfile.TemporaryDirectory()
        self._data = tempfile.TemporaryDirectory()
        self._saved = {
            key: os.environ.get(key)
            for key in ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_DATA")
        }
        os.environ["CLAUDE_PROJECT_DIR"] = self._project.name
        os.environ["CLAUDE_PLUGIN_DATA"] = self._data.name

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._project.cleanup()
        self._data.cleanup()

    @property
    def project(self):
        return self._project.name

    @property
    def data(self):
        return self._data.name

    def event(self, session=SESSION, **extra):
        record = {"session_id": session, "cwd": self.project}
        record.update(extra)
        return record

    def path(self, name):
        return os.path.join(self.project, name)

    def touch(self, name="app.py", mtime=None, content="x\n"):
        """Create or modify a file, optionally pinning its mtime."""
        path = self.path(name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(content)
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path

    def edit(self, name="app.py", now=150.0, session=SESSION):
        """What the PostToolUse(Write|Edit) hook does: Claude changed a file."""
        path = self.touch(name, mtime=now)
        return session_state.record_edit(path, self.event(session), now=now)

    def shell(self, command, start, end, session=SESSION):
        """What the PostToolUse(Bash|PowerShell) hook does for a shell call."""
        duration_ms = int((end - start) * 1000)
        return session_state.record_shell(
            command, self.event(session, duration_ms=duration_ms), now=end
        )

    def check(self, exit_code, now, command="pytest", session=SESSION):
        return session_state.record_check(
            command, exit_code, self.event(session), now=now
        )

    def blocked(self, session=SESSION):
        return session_state.unverified(self.event(session))


class TestGateLogic(StateTestCase):
    def test_clean_session_is_not_blocked(self):
        blocked, _ = self.blocked()
        self.assertFalse(blocked)

    def test_change_without_verification_blocks(self):
        self.edit("app.py", now=150.0)
        blocked, reason = self.blocked()
        self.assertTrue(blocked)
        self.assertIn("app.py changed this session, and no check has passed", reason)

    def test_first_edit_of_a_session_counts(self):
        """0.2.1 set its session baseline in the same hook that reported the
        first edit, after the edit, so a session's first edit never counted."""
        self.edit("app.py", now=time.time())
        blocked, _ = self.blocked()
        self.assertTrue(blocked)

    def test_passing_check_after_change_clears(self):
        self.edit("app.py", now=150.0)
        self.check(0, now=160.0)
        blocked, _ = self.blocked()
        self.assertFalse(blocked)

    def test_change_after_passing_check_rearms(self):
        """The property that makes this a ratchet rather than a checkbox."""
        self.edit("app.py", now=150.0)
        self.check(0, now=160.0)
        self.edit("app.py", now=170.0)
        blocked, reason = self.blocked()
        self.assertTrue(blocked)
        self.assertIn("`pytest` passed, but app.py changed afterwards", reason)

    def test_failing_check_does_not_clear(self):
        self.edit("app.py", now=150.0)
        self.check(1, now=160.0)
        blocked, reason = self.blocked()
        self.assertTrue(blocked)
        self.assertIn("exited 1", reason)

    def test_latest_check_wins(self):
        """A pass followed by a failure leaves the work unverified."""
        self.edit("app.py", now=150.0)
        self.check(0, now=160.0)
        self.check(2, now=170.0)
        blocked, reason = self.blocked()
        self.assertTrue(blocked)
        self.assertIn("exited 2", reason)

    def test_prose_change_does_not_block(self):
        self.edit("NOTES.md", now=150.0)
        blocked, _ = self.blocked()
        self.assertFalse(blocked)

    def test_reason_names_the_file_relative_to_the_project(self):
        self.edit(os.path.join("src", "deep", "mod.kt"), now=150.0)
        _, reason = self.blocked()
        self.assertIn("src/deep/mod.kt changed this session", reason)
        self.assertNotIn(self.project, reason)


class TestOnlyClaudesChangesCount(StateTestCase):
    """The audit's clone false alarm: files Claude did not write were held
    against it. A change counts only if Claude made it, through a file tool or
    inside the window of one of its own shell calls."""

    def test_file_changed_outside_any_claude_tool_does_not_block(self):
        """A program, an editor or a sync tool wrote it, not Claude."""
        self.edit("NOTES.md", now=100.0)
        self.touch("app.py", mtime=150.0)
        blocked, _ = self.blocked()
        self.assertFalse(blocked)

    def test_shell_write_inside_a_window_blocks(self):
        """The WatchersScreen.kt catch: Claude edited Kotlin through a shell
        script, which fires no Write|Edit hook."""
        self.shell("python fix_screens.py", start=140.0, end=160.0)
        self.touch("app/WatchersScreen.kt", mtime=150.0)
        blocked, reason = self.blocked()
        self.assertTrue(blocked)
        self.assertIn("app/WatchersScreen.kt changed this session", reason)

    def test_shell_write_outside_every_window_does_not_block(self):
        self.shell("ls", start=140.0, end=141.0)
        self.touch("app.py", mtime=150.0)
        blocked, _ = self.blocked()
        self.assertFalse(blocked)

    def test_window_without_duration_reaches_back_to_the_bash_timeout(self):
        """duration_ms is optional in the hook input. Without it, the window
        reaches back the longest a foreground shell call can run."""
        session_state.record_shell("make gen", self.event(), now=1000.0)
        self.touch("gen.py", mtime=1000.0 - 300)
        blocked, _ = self.blocked()
        self.assertTrue(blocked)

    def test_clone_does_not_count(self):
        """The REA false alarm: every file a clone produced was 'unverified'."""
        self.shell("git clone https://github.com/x/rea.git .", start=140.0, end=160.0)
        self.touch("website/wrangler.toml", mtime=150.0)
        self.touch("website/src/index.js", mtime=150.0)
        blocked, _ = self.blocked()
        self.assertFalse(blocked)

    def test_fetch_and_checkout_does_not_count(self):
        """What REA actually ran once the clone into `.` failed."""
        self.shell(
            "git init -q && git remote add origin https://x/rea.git && "
            "git fetch -q origin && git checkout -q -b main origin/main",
            start=140.0, end=160.0,
        )
        self.touch("website/src/index.js", mtime=150.0)
        blocked, _ = self.blocked()
        self.assertFalse(blocked)

    def test_git_with_global_options_is_still_recognised(self):
        self.shell("git -C /c/x pull --ff-only", start=140.0, end=160.0)
        self.touch("app.py", mtime=150.0)
        blocked, _ = self.blocked()
        self.assertFalse(blocked)

    def test_read_only_git_command_still_counts_its_window(self):
        """Only working-tree git commands are exempt: `git status && sed -i`
        is still Claude editing code."""
        self.shell("git status && sed -i s/a/b/ app.py", start=140.0, end=160.0)
        self.touch("app.py", mtime=150.0)
        blocked, _ = self.blocked()
        self.assertTrue(blocked)

    def test_edit_outside_the_project_does_not_count(self):
        """Scratch scripts in the session scratchpad are not the user's work."""
        with tempfile.TemporaryDirectory() as elsewhere:
            path = os.path.join(elsewhere, "probe.py")
            open(path, "w").close()
            session_state.record_edit(path, self.event(), now=150.0)
        blocked, _ = self.blocked()
        self.assertFalse(blocked)

    def test_program_written_session_file_does_not_count(self):
        """The Telethon false alarm: a script Claude ran wrote its session file."""
        self.shell("python tg_dedupe.py --dry-run", start=140.0, end=160.0)
        self.touch("tg_dedupe_session.session", mtime=150.0)
        blocked, _ = self.blocked()
        self.assertFalse(blocked)

    def test_synced_extensionless_config_does_not_count(self):
        """The config/router/wireless false alarm: a sync script Claude ran
        rewrote UCI config files, which have no extension."""
        self.shell(r"& .\scripts\pc\sync_router_config.ps1", start=140.0, end=160.0)
        self.touch("config/router/wireless", mtime=150.0,
                   content="config wifi-device 'radio0'\n")
        blocked, _ = self.blocked()
        self.assertFalse(blocked)


class TestEditClassification(StateTestCase):
    def test_prose_edits_do_not_arm_the_gate(self):
        for name in ("README.md", "notes.txt"):
            with self.subTest(name=name):
                self.assertFalse(session_state.is_code(name))

    def test_ratchet_own_files_do_not_arm_the_gate(self):
        self.assertFalse(session_state.is_code(".claude/framework/session-state.json"))
        self.assertFalse(session_state.is_code("/proj/.claude/PROJECT_PROFILE.md"))

    def test_code_edits_arm_the_gate(self):
        for path in ("a.py", "b.kt", "c.ts", "src/d.go", "Makefile", "e.ps1",
                     "f.sh", "Dockerfile"):
            with self.subTest(path=path):
                self.assertTrue(session_state.is_code(path))

    def test_config_formats_count_as_code(self):
        """HTML, JSON and YAML were ruled code in September; TOML joins them."""
        for path in ("index.html", "package.json", "ci.yml", "c.yaml",
                     "website/wrangler.toml", "Cargo.toml"):
            with self.subTest(path=path):
                self.assertTrue(session_state.is_code(path))

    def test_dotfiles_do_not_arm_the_gate(self):
        """.gitignore x4, .gitattributes x3 and .env.example x1 in the audit."""
        for path in (".gitignore", ".gitattributes", ".env.example",
                     "sub/.editorconfig", r"C:\proj\.gitignore"):
            with self.subTest(path=path):
                self.assertFalse(session_state.is_code(path))

    def test_example_and_session_files_do_not_arm_the_gate(self):
        for path in ("config.yaml.example", "settings.example",
                     "tg_dedupe_session.session"):
            with self.subTest(path=path):
                self.assertFalse(session_state.is_code(path))

    def test_extensionless_file_counts_only_with_a_shebang(self):
        self.touch("config/router/wireless", content="config wifi-device 'radio0'\n")
        self.touch("bin/deploy", content="#!/usr/bin/env bash\necho hi\n")
        self.assertFalse(session_state.is_code("config/router/wireless", self.project))
        self.assertTrue(session_state.is_code("bin/deploy", self.project))
        self.assertFalse(session_state.is_code("does/not/exist", self.project))

    def test_windows_separators_are_handled(self):
        self.assertFalse(session_state.is_code(r"proj\.claude\thing.json"))
        self.assertTrue(session_state.is_code(r"proj\src\app.py"))

    def test_prose_edit_records_nothing(self):
        self.assertFalse(
            session_state.record_edit(self.touch("README.md"), self.event())
        )


class TestSessions(StateTestCase):
    def test_another_sessions_edit_does_not_block(self):
        self.edit("app.py", now=150.0, session="other")
        blocked, _ = self.blocked(session=SESSION)
        self.assertFalse(blocked)

    def test_another_sessions_pass_does_not_clear(self):
        self.edit("app.py", now=150.0)
        self.check(0, now=160.0, session="other")
        blocked, _ = self.blocked()
        self.assertTrue(blocked)

    def test_projects_are_kept_apart(self):
        self.edit("app.py", now=150.0)
        with tempfile.TemporaryDirectory() as second:
            os.environ["CLAUDE_PROJECT_DIR"] = second
            blocked, _ = session_state.unverified(
                {"session_id": SESSION, "cwd": second}
            )
            os.environ["CLAUDE_PROJECT_DIR"] = self.project
        self.assertFalse(blocked)
        self.assertTrue(self.blocked()[0])

    def test_stale_events_from_other_sessions_are_pruned(self):
        log = hook_io.event_log_path(self.event())
        now = time.time()
        stale = now - 3 * 24 * 3600
        self.edit("old.py", now=stale, session="long-gone")
        self.edit("mine.py", now=stale)  # this session's own, however old
        self.edit("recent.py", now=now - 60, session="neighbour")
        session_state.unverified(self.event(), now=now)
        with open(log, "r", encoding="utf-8") as handle:
            text = handle.read()
        self.assertNotIn("old.py", text)
        self.assertIn("mine.py", text)
        self.assertIn("recent.py", text)


class TestStateLocation(StateTestCase):
    def test_event_log_lives_under_plugin_data(self):
        self.edit("app.py", now=150.0)
        log = hook_io.event_log_path(self.event())
        self.assertTrue(os.path.isfile(log))
        self.assertTrue(
            os.path.normcase(log).startswith(os.path.normcase(self.data)), log
        )

    def test_nothing_is_written_into_the_project(self):
        """State in the project broke `git clone <url> .` into a fresh folder."""
        self.edit("app.py", now=150.0)
        self.shell("ls", 140.0, 160.0)
        self.check(0, now=170.0)
        session_state.note_block(self.event())
        self.blocked()
        self.assertEqual(sorted(os.listdir(self.project)), ["app.py"])

    def test_same_project_spelled_differently_shares_a_log(self):
        a = hook_io.event_log_path({"cwd": "ignored"})
        os.environ["CLAUDE_PROJECT_DIR"] = self.project.replace("\\", "/") + "/"
        b = hook_io.event_log_path({"cwd": "ignored"})
        self.assertEqual(os.path.normcase(a), os.path.normcase(b))

    def test_without_plugin_data_nothing_is_recorded(self):
        os.environ.pop("CLAUDE_PLUGIN_DATA")
        self.assertFalse(
            session_state.record_edit(self.touch("app.py"), self.event())
        )
        self.assertEqual(self.blocked(), (False, None))
        self.assertEqual(sorted(os.listdir(self.project)), ["app.py"])


class TestBlockLimit(StateTestCase):
    def test_gate_gives_up_rather_than_trapping(self):
        """A Stop hook that cannot be satisfied is worse than one that yields."""
        self.assertTrue(session_state.note_block(self.event()))   # 1st nudge
        self.assertTrue(session_state.note_block(self.event()))   # 2nd nudge
        self.assertFalse(session_state.note_block(self.event()))  # give up

    def test_new_edit_rearms_the_nudges(self):
        for _ in range(3):
            session_state.note_block(self.event())
        self.edit("src/app.py", now=time.time())
        self.assertTrue(session_state.note_block(self.event()))

    def test_passing_check_rearms_the_nudges(self):
        for _ in range(3):
            session_state.note_block(self.event())
        self.check(0, now=time.time())
        self.assertTrue(session_state.note_block(self.event()))

    def test_blocks_count_per_session(self):
        for _ in range(3):
            session_state.note_block(self.event(session="other"))
        self.assertTrue(session_state.note_block(self.event()))


class TestCorruptState(StateTestCase):
    def test_garbage_lines_are_skipped(self):
        self.edit("app.py", now=150.0)
        with open(hook_io.event_log_path(self.event()), "a", encoding="utf-8") as handle:
            handle.write("{not json\n[]\n")
        blocked, _ = self.blocked()
        self.assertTrue(blocked)

    def test_wholly_corrupt_log_degrades_to_nothing(self):
        log = hook_io.event_log_path(self.event())
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        self.assertEqual(self.blocked(), (False, None))


def run_script(name, args=None, env=None, stdin=""):
    environment = dict(os.environ)
    # As ratchet-hook.sh does: no __pycache__/ in plugin/, which gets installed.
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        environment.update(env)
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS_DIR, name)] + (args or []),
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
    )


class TestVerifyRun(StateTestCase):
    # `exit N` is one of the few command forms cmd.exe and sh both honour.
    PASS = "exit 0"
    FAIL = "exit 3"

    def test_passing_command_exits_zero(self):
        proc = run_script("verify_run.py", ["--command", self.PASS])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("passed", proc.stdout)

    def test_failing_command_returns_its_real_exit_code(self):
        """A pass cannot be asserted: the exit code is the command's own."""
        proc = run_script("verify_run.py", ["--command", self.FAIL])
        self.assertEqual(proc.returncode, 3)

    def test_writes_no_state_of_its_own(self):
        """The PostToolUse hook that sees this script's exit records the
        receipt; a second writer could only disagree with it."""
        run_script("verify_run.py", ["--command", self.PASS])
        self.assertEqual(os.listdir(self.data), [])
        self.assertEqual(os.listdir(self.project), [])

    def test_quoted_argument_is_not_resplit(self):
        """Regression: the command was once rejoined from argv, which dropped
        quoting and let the shell re-split it into separate commands."""
        marker = os.path.join(self.project, "marker.txt").replace("\\", "/")
        command = '{} -c "open(r\'{}\', \'w\').write(\'x\')"'.format(
            sys.executable, marker
        )
        proc = run_script("verify_run.py", ["--command", command])
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertTrue(os.path.isfile(marker), "quoted -c argument was mangled")

    def test_session_flag_is_still_accepted(self):
        """Existing instructions pass --session; it must not become an error."""
        proc = run_script(
            "verify_run.py",
            ["--session", "${CLAUDE_SESSION_ID}", "--command", self.PASS],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_no_command_is_an_error(self):
        for args in ([], ["--command", "   "]):
            with self.subTest(args=args):
                proc = run_script("verify_run.py", args)
                self.assertEqual(proc.returncode, 2)


class TestStopHook(StateTestCase):
    def _run(self, event=None, env=None):
        return run_script(
            "require_verification.py",
            env=env,
            stdin=json.dumps(event if event is not None else self.event()),
        )

    def test_blocks_on_unverified_changes(self):
        self.edit("app.py", now=150.0)
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        # Top-level, not nested under hookSpecificOutput: the nested shape is
        # PreToolUse's, and Claude Code ignores it on Stop. A hook that emits it
        # looks like it works and blocks nothing.
        self.assertNotIn("hookSpecificOutput", payload)
        self.assertEqual(payload["decision"], "block")
        reason = payload["reason"]
        self.assertIn("without a passing check", reason)
        self.assertIn("no check has passed", reason)

    def test_reason_says_how_to_clear_the_gate(self):
        self.edit("app.py", now=150.0)
        reason = json.loads(self._run().stdout)["reason"]
        self.assertIn("PROJECT_PROFILE.md", reason)
        self.assertIn("pipe", reason)
        self.assertIn("verify_run.py", reason)

    def test_silent_when_nothing_changed(self):
        self.assertEqual(self._run().stdout.strip(), "")

    def test_silent_after_a_passing_check(self):
        self.edit("app.py", now=150.0)
        self.check(0, now=160.0)
        self.assertEqual(self._run().stdout.strip(), "")

    def test_respects_stop_hook_active(self):
        self.edit("app.py", now=150.0)
        proc = self._run(self.event(stop_hook_active=True))
        self.assertEqual(proc.stdout.strip(), "")

    def test_gives_up_after_repeated_blocks(self):
        self.edit("app.py", now=150.0)
        self.assertIn("block", self._run().stdout)
        self.assertIn("block", self._run().stdout)
        final = self._run().stdout
        self.assertNotIn('"decision"', final)
        self.assertIn("letting this turn end", final)

    def test_says_the_gate_is_off_without_plugin_data(self):
        env = dict(os.environ)
        env.pop("CLAUDE_PLUGIN_DATA")
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "require_verification.py")],
            input=json.dumps(self.event()), capture_output=True, text=True,
            encoding="utf-8", env=dict(env, PYTHONDONTWRITEBYTECODE="1"),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("CLAUDE_PLUGIN_DATA", proc.stdout)
        self.assertNotIn('"decision"', proc.stdout)

    def test_exits_zero_on_garbage_input(self):
        proc = run_script("require_verification.py", stdin="not json")
        self.assertEqual(proc.returncode, 0)


class TestUtf8Output(StateTestCase):
    """Piped Python stdout on Windows is the ANSI code page unless UTF-8 mode
    is on, which turned the reason's em dash into U+FFFD in the transcript."""

    def _env(self):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="0")
        env.pop("PYTHONIOENCODING", None)
        return env

    def test_block_reason_is_utf8_without_utf8_mode(self):
        self.edit("app.py", now=150.0)
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "require_verification.py")],
            input=json.dumps(self.event()).encode("utf-8"),
            capture_output=True, env=self._env(),
        )
        text = proc.stdout.decode("utf-8")  # strict: raises on cp1252 bytes
        self.assertIn("\u2014", json.loads(text)["reason"])

    def test_non_ascii_input_survives_without_utf8_mode(self):
        name = "caf\u00e9 \u2014 \u00fc.py"
        path = self.touch(name)
        event = self.event(tool_name="Write", tool_input={"file_path": path})
        subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "check_file_size.py")],
            input=json.dumps(event, ensure_ascii=False).encode("utf-8"),
            capture_output=True, env=self._env(),
        )
        _, reason = self.blocked()
        self.assertIn(name, reason or "")


@unittest.skipIf(shutil.which("git") is None, "git not on PATH")
class TestCloneIntoFreshFolder(StateTestCase):
    def test_clone_into_dot_works_after_the_hooks_ran(self):
        """End to end, the REA failure: the hooks fire on the first tool call,
        then `git clone <url> .` must still find the folder empty."""
        source = os.path.join(self.data, "source")
        os.makedirs(source)
        empty = os.path.join(self.data, "empty.gitconfig")
        open(empty, "w").close()
        git_env = dict(os.environ, GIT_CONFIG_GLOBAL=empty, GIT_CONFIG_NOSYSTEM="1")

        def git(*args, cwd):
            return subprocess.run(["git", *args], cwd=cwd, env=git_env,
                                  capture_output=True, text=True)

        git("init", "-q", cwd=source)
        with open(os.path.join(source, "a.py"), "w") as handle:
            handle.write("x = 1\n")
        git("add", "-A", cwd=source)
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "i",
            cwd=source)

        for script, event in (
            ("log_tool_call.py", self.event(tool_name="Bash",
                                            tool_input={"command": "ls"})),
            ("check_file_size.py", self.event(tool_name="Write", tool_input={
                "file_path": os.path.join(self.data, "elsewhere.py")})),
            ("require_verification.py", self.event()),
        ):
            run_script(script, stdin=json.dumps(event))

        clone = git("clone", "-q", source, ".", cwd=self.project)
        self.assertEqual(clone.returncode, 0, clone.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
