---
description: Applies a build-least-code decision ladder before writing new code. Use whenever about to add a new function, file, dependency, or abstraction.
---

# Minimalism

Before writing new code, work down this ladder and stop at the first "yes":

1. **Does this need to exist at all?** (YAGNI — don't build for a hypothetical future need)
2. **Is it already in the codebase?** Reuse over rewrite.
3. **Is it in the language's standard library?** Prefer built-ins over new dependencies.
4. **Is it a native platform/framework feature?** Leverage what's already available before adding code.
5. **Is it in an already-installed dependency?** Use what's already there before adding a new one.
6. **Can it be one line?** Minimize verbosity.
7. **Only then:** write the minimum code that solves the actual problem.

This ladder applies *after* you understand the problem — read the surrounding code thoroughly first. Being lazy about the solution is the goal; being lazy about reading is not. Never skip validation, error handling, or security-relevant checks to make code shorter — minimalism trims unneeded abstraction and duplication, not correctness.
