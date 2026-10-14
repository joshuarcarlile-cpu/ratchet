#!/usr/bin/env bash
# A freshly checked-out repo whose files are newer than the session start.
set -e
git init -q
mkdir -p .claude
mkdir -p website/src
cat > .claude/PROJECT_PROFILE.md <<'EOF'
# Project Profile

## Commands
- Test: `npm test --prefix website`
EOF
printf '# Changelog\n\n## Unreleased\n' > CHANGELOG.md
cat > website/wrangler.toml <<'EOF'
name = "rea-site"
main = "src/index.js"
compatibility_date = "2026-09-01"
EOF
printf 'export default { fetch() { return new Response("ok"); } };\n' > website/src/index.js
printf '# REA\n' > README.md
git add -A
git -c user.name=fixture -c user.email=fixture@example.com commit -qm init
touch -d '+1 hour' website/src/index.js README.md
touch -d '+2 hours' website/wrangler.toml
