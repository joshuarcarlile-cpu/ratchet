#!/usr/bin/env bash
# A Telethon bot whose session file changed during the session.
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
printf 'from telethon import TelegramClient\n' > tg_dedupe.py
printf 'import tg_dedupe\n' > test_main.py
printf '# tg dedupe\n\nFinds duplicate media in a Telegram group.\n' > README.md
git add -A
git -c user.name=fixture -c user.email=fixture@example.com commit -qm init
printf 'SQLite format 3\000' > tg_dedupe_session.session
touch -d '+1 hour' tg_dedupe_session.session
