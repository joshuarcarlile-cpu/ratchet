#!/usr/bin/env bash
# Verify that ratchet's hooks work on this machine, then say how to install it.
#
# Claude Code installs ratchet itself, from the GitHub marketplace, so this
# copies and registers nothing. It does the part a plugin manager cannot: prove
# the hook scripts actually work here before you let them gate your work.
#
# It deliberately does not register this folder as a marketplace: a local
# folder source loads the working copy in place, so an unfinished edit here
# would reach every session on the machine.
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
else
    echo "-- claude CLI not found; skipping manifest validation."
fi

echo ""
echo "Done. To install, in Claude Code:"
echo "  /plugin marketplace add joshuarcarlile-cpu/ratchet"
echo "  /plugin install ratchet@ratchet-marketplace"
echo ""
echo "Then run /project-profile once per project so the verification gate"
echo "knows what your check command is."
