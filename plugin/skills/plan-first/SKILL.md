---
description: Enforces explore-plan-review-implement-verify discipline for any non-trivial change. Use before starting work that touches multiple files, changes behavior, or whose approach isn't obvious.
---

# Plan First

1. Read `.claude/PROJECT_PROFILE.md` (run `project-profile` first if it's missing) and the code the change touches. Don't edit yet.
2. Write a short plan: what changes, in which files, and the check that will prove it worked, drawn from the profile's commands.
3. Present the plan and wait for the user's go-ahead before writing code. Silence, a vague reply or an unrelated question is not approval. The one exception is a request that says outright not to wait for approval, as an unattended `claude -p` job may: then put the plan in your reply first, and proceed.
4. Implement, then run the check with the `verify` skill and show its real output. If it fails, fix and re-run, but stop after 2 consecutive failures with the same error or 4 runs in all, and report what fails and what you tried. Never call a change complete while its check is failing or hasn't run.

This applies whether or not plan mode is on. Skip it for genuinely trivial changes (a typo, a log line, a one-line rename) whose diff fits in one sentence.
