#!/usr/bin/env bash
cat > package.json <<'EOF'
{
  "name": "fixture",
  "scripts": { "test": "jest" }
}
EOF
