#!/usr/bin/env bash
cat > handler.py <<'EOF'
from config import get_setting
from data_access import fetch_record


def handle_request(record_id):
    ttl = get_setting("cache_ttl")
    return fetch_record(record_id)
EOF
cat > data_access.py <<'EOF'
def fetch_record(record_id):
    # pretend database lookup
    return {"id": record_id, "value": "example"}
EOF
cat > config.py <<'EOF'
SETTINGS = {"cache_ttl": 60}


def get_setting(key):
    return SETTINGS[key]
EOF
