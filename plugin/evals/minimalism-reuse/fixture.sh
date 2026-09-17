#!/usr/bin/env bash
cat > utils.py <<'EOF'
import re


def slugify(text: str) -> str:
    """Lowercase, replace non-alphanumerics with hyphens."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
EOF
