#!/usr/bin/env bash
# Verify and register ratchet as a local Claude Code marketplace.
#
# Claude Code manages plugin installation itself, so this does not copy files
# into a plugin directory. It does the part a plugin manager cannot: prove the
# hook scripts actually work on this machine before you let them gate your work.
set -e

echo "============================================================"
echo " ratchet - workflow discipline for Claude Code"
echo "============================================================"

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Interpreter. The hooks are Python; the shell wrappers only dispatch.
PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c "" >/dev/null 2>&1; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "!! No working Python interpreter on PATH." >&2
    echo "   ratchet's hooks need one. Install Python 3 and re-run." >&2
    exit 1
fi
echo "-> Python: $($PYTHON --version 2>&1)"

# 2. Run the hook tests. A hook that mangles its own input is worse than no
#    hook, so this is the step worth having.
echo "-> Verifying hook logic..."
"$PYTHON" -m unittest discover -s "${REPO_DIR}/plugin/scripts/tests" -p "test_*.py" -q

# 3. Validate the plugin manifest, if the CLI is present.
if command -v claude >/dev/null 2>&1; then
    echo "-> Validating plugin manifest..."
    claude plugin validate "${REPO_DIR}/plugin"

    echo "-> Registering local marketplace..."
    claude plugin marketplace add "${REPO_DIR}"
else
    echo "-- claude CLI not found; skipping validation and registration."
fi

chmod +x "${REPO_DIR}/plugin/bin/ratchet-hook.sh" 2>/dev/null || true

echo ""
echo "Done. To finish:"
echo "  /plugin install ratchet"
echo ""
echo "Then run /project-profile once per project so the verification gate"
echo "knows what your check command is."
