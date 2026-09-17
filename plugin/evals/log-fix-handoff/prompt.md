---
max_turns: 8
allowed_tools: [Read, Glob, Grep, Skill, Agent, Write, Edit]
---

I just fixed a bug: get_user_name(user) crashed with an AttributeError when user.profile was None, because it tried to read .name off None. I added the null check that returns "unknown" in that case, and confirmed it works. Please log this fix.
