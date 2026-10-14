#!/usr/bin/env bash
# A home-lab repo with PC scripts, as in network-stuff.
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
mkdir -p scripts/pc
cat > scripts/pc/register_pc_backup_tasks.ps1 <<'EOF'
param([string]$At = '03:00')
$trigger = New-ScheduledTaskTrigger -Daily -At $At
Write-Output "backup task at $At"
EOF
git add -A
git -c user.name=fixture -c user.email=fixture@example.com commit -qm init
