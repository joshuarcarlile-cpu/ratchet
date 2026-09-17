#!/usr/bin/env bash
mkdir -p .claude
cat > .claude/PROJECT_PROFILE.md <<'EOF'
# Project Profile

## Language(s)
- Python: pyproject.toml present

## Commands
- Test: `pytest`

## Conventions
- Tests live in: `tests/`
- Scripts live in: `scripts/`

## Gotchas
EOF
mkdir -p tests
cat > user.py <<'EOF'
def get_user_name(user):
    if user.profile is None:
        return "unknown"
    return user.profile.name
EOF
cat > tests/test_user.py <<'EOF'
from user import get_user_name


class Profile:
    def __init__(self, name):
        self.name = name


class User:
    def __init__(self, profile):
        self.profile = profile


def test_get_user_name_with_profile():
    assert get_user_name(User(Profile("Alice"))) == "Alice"
EOF
