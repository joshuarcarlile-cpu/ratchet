#!/usr/bin/env bash
# A small Python project, as in Duplicate check.
set -e
git init -q
mkdir -p .claude
cat > .claude/PROJECT_PROFILE.md <<'EOF'
# Project Profile

## Commands
- Test: `python -B test_main.py`
- Lint/build: none
EOF
printf '# Changelog\n\n## Unreleased\n' > CHANGELOG.md
printf 'print("hi")\n' > main.py
printf 'import main\n' > test_main.py
printf '__pycache__/\n.venv/\n' > .gitignore
git add -A
git -c user.name=fixture -c user.email=fixture@example.com commit -qm init
