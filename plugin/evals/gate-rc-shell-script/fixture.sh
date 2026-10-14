#!/usr/bin/env bash
# A home-lab repo with server scripts, as in network-stuff.
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
mkdir -p scripts/server
cat > scripts/server/router_probes.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
probe() { printf '== %s\n' "$1"; shift; "$@"; }
probe "date" date
EOF
git add -A
git -c user.name=fixture -c user.email=fixture@example.com commit -qm init
