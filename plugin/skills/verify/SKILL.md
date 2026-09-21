---
name: verify
description: Runs the project's check command and shows its real output, recording the result so the verification gate can tell whether work was actually checked. Use after making a change, and whenever the Stop hook reports unverified edits.
---

# Verify

1. Read `.claude/PROJECT_PROFILE.md` for the project's **Test** command (and
   lint/build, if the change warrants it). If the profile is missing, run the
   `project-profile` skill first — the command has to come from somewhere other
   than a guess.

2. Run it **through ratchet's runner**, not directly:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/ratchet-hook.sh" verify_run.py --session "${CLAUDE_SESSION_ID}" --command "<the check command>"
   ```

   Pass the command as one quoted string, exactly as the profile records it.

   The runner streams the command's output unchanged and exits with its real
   exit code. It records the receipt that clears the verification gate, and it
   only records a pass when the command actually exits 0 — which is why running
   the command directly does not clear the gate.

3. Show the actual output. Not "tests pass", not "should work now" — the output.

4. If it fails, keep working. A failing check is the signal to fix the code, not
   to explain the failure and move on. Re-run this skill after each attempt.

If the profile records no check command and none can be found in the project
(no test script, no CI config, no test directory), say so plainly and stop.
Ratchet would rather report that a project has no check than invent one that
proves nothing.
