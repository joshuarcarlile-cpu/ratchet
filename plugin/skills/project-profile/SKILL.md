---
description: Detects the host project's language, test runner, lint/build commands, and conventional test/script locations, then records them in .claude/PROJECT_PROFILE.md. Use at the start of work in a project that doesn't have a profile yet, or when the detected profile looks stale.
---

# Project Profile

1. Check for `.claude/PROJECT_PROFILE.md`. If it exists and looks current (referenced files/commands still exist), stop — nothing to do.
2. Otherwise, detect language(s) from marker files in the project root:
   - `package.json` → Node/JavaScript/TypeScript
   - `pyproject.toml`, `setup.py`, or `requirements.txt` → Python
   - `go.mod` → Go
   - `Cargo.toml` → Rust
   - `*.csproj` or `*.sln` → C#
   - `Gemfile` → Ruby
   A project can have more than one; record all that apply.
3. For each detected language, infer:
   - **Test command** (e.g. `npm test`, `pytest`, `go test ./...`, `cargo test`) — check `package.json` scripts, a `Makefile`, or CI config before guessing the ecosystem default.
   - **Lint/build command**, if discoverable the same way.
   - **Conventional test directory** (e.g. `tests/`, `__tests__/`, `src/**/*.test.ts`).
4. Write `.claude/PROJECT_PROFILE.md`:

   ```markdown
   # Project Profile

   ## Language(s)
   - <language>: <evidence, e.g. "package.json present">

   ## Commands
   - Test: `<command>`
   - Lint/build: `<command>`

   ## Conventions
   - Tests live in: `<dir>`
   - Scripts live in: `<dir>`

   ## Gotchas
   <!-- appended to by the log-fix skill -->
   ```

5. Keep the whole file under ~40 lines. Every other skill and the `regression-writer` subagent reads it, so it has to stay cheap to load — don't pad it with explanations.
