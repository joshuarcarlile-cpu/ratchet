#!/usr/bin/env bash
# A Python project that reads two environment variables.
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
cat > main.py <<'EOF'
import os

API_ID = os.environ["API_ID"]
API_HASH = os.environ["API_HASH"]
EOF
printf 'import main\n' > test_main.py
git add -A
git -c user.name=fixture -c user.email=fixture@example.com commit -qm init
