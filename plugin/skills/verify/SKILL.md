---
description: Runs the project's check command and shows its real output, so the verification gate can tell whether work was actually checked. Use after making a change, and whenever the Stop hook reports unverified edits.
---

# Verify

1. Read `.claude/PROJECT_PROFILE.md` for the project's **Test** command (and
   lint/build, if the change warrants it). If the profile is missing, run the
   `project-profile` skill first — the command has to come from somewhere other
   than a guess.

2. Run the Test command through the Bash or PowerShell tool, exactly as the
   profile writes it. Ratchet records the result from that tool call's own exit
   code, so:

   - Nothing after it but redirections or `&&`. A pipe (`| tail`,
     `| Select-String`), `;` or `||` replaces the check's exit code, and then
     nothing is recorded. To keep long output short, redirect it to a file
     outside the project, such as the session scratchpad
     (`> <scratchpad>/check.log 2>&1`), and read what you need from it.
   - No extra arguments. A filtered run (`-k`, `--tests`) is not the check.
   - Setup before it is fine: `cd <dir> && <check>`.

   For a check the profile doesn't list, such as `bash -n` on the script that
   changed, run it through ratchet's runner, which records its `--command`:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/ratchet-hook.sh" verify_run.py --command "<the check command>"
   ```

   The runner uses the platform's default shell (cmd.exe on Windows), and the
   same no-pipe rule applies to it.

3. Show the actual output. Not "tests pass", not "should work now" — the output.

4. If it fails, fix the code and run it again. Stop after 2 consecutive runs
   that fail with the same error, or after 4 runs in all, and report the
   failing output, what you tried, and your best diagnosis. A failing check is
   never reported as done.

If the profile records no check command and none can be found in the project
(no test script, no CI config, no test directory), say so plainly and stop.
Ratchet would rather report that a project has no check than invent one that
proves nothing.
