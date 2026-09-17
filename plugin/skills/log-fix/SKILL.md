---
description: Hands off to the regression-writer subagent after a bug is fixed and confirmed working. Use once, right after verifying a fix, not as part of diagnosing it.
---

# Log Fix

Once a bug fix has been verified (per the `plan-first` verification step — the failing check now passes), delegate to the `regression-writer` subagent with a one-paragraph description covering:

- What was broken and how it showed up.
- The root cause.
- What changed to fix it.

Do this once per confirmed fix. Don't invoke it speculatively while still diagnosing, and don't invoke it again for the same bug.
