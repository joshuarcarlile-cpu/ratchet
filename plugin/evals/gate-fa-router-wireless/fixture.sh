#!/usr/bin/env bash
# A home-lab repo with OpenWrt UCI config, as in network-stuff.
set -e
git init -q
mkdir -p .claude
mkdir -p docs
cat > .claude/PROJECT_PROFILE.md <<'EOF'
# Project Profile

## Commands
- Test: none. No test suite exists.
- Lint/build: none recorded. Per-change checks: `bash -n <file>`; PowerShell ParseFile.
EOF
printf '# Changelog\n\n## Unreleased\n' > docs/changelog.md
mkdir -p config/router
cat > config/router/wireless <<'EOF'
config wifi-device 'radio0'
	option type 'mac80211'
	option country 'US'
EOF
git add -A
git -c user.name=fixture -c user.email=fixture@example.com commit -qm init
