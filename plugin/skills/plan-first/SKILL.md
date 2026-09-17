---
description: Enforces explore-plan-review-implement-verify discipline for any non-trivial change. Use before starting work that touches multiple files, changes behavior, or whose approach isn't obvious.
---

# Plan First

1. Read `.claude/PROJECT_PROFILE.md`. If it's missing, run the `project-profile` skill first.
2. Explore the relevant code read-only. Do not edit yet.
3. Write a short plan covering: what changes, which files, and — mandatory — what check proves it worked (a test, build, or screenshot command, drawn from the profile's commands).
4. Present the plan and explicitly wait for the user's go-ahead before writing any code. Do not treat silence, a vague reply, or an unrelated follow-up question as approval.
5. Implement the change, then run the verification check named in step 3 and show its actual output — not just "done" or "should work now."
6. If the check fails, keep iterating. Never report a change as complete while the check is failing or hasn't been run.

Skip this whole flow for genuinely trivial changes (a typo, a log line, a one-line rename) where the diff could be described in a single sentence — planning overhead isn't worth it there.

This applies whether or not interactive plan mode is toggled on, including in headless (`-p`) runs, since there's no user available mid-run to catch a skipped step.
