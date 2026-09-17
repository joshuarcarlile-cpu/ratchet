#!/usr/bin/env bash
mkdir -p .claude/framework
cat > .claude/framework/tool-log.jsonl <<'EOF'
{"ts":1,"cmd":"curl -s https://api.example.com/v1/users/123 | jq .name"}
{"ts":2,"cmd":"git status"}
{"ts":3,"cmd":"curl -s https://api.example.com/v1/users/456 | jq .name"}
{"ts":4,"cmd":"git diff"}
{"ts":5,"cmd":"curl -s https://api.example.com/v1/users/789 | jq .name"}
{"ts":6,"cmd":"curl -s https://api.example.com/v1/users/321 | jq .name"}
EOF
