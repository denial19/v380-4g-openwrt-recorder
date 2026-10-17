#!/bin/sh
# Execute in repo working tree, does not tag or push.
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
python3 -m compileall -q src tests scripts
python3 -m unittest discover -s tests -v
python3 scripts/security_audit.py
if ! git diff --check; then
    echo 'ERROR: whitespace errors in changed tracked files' >&2
    exit 1
fi
if ! git diff --cached --check; then
    echo 'ERROR: whitespace errors in staged files' >&2
    exit 1
fi
echo '[OK] Local source checks done. Real hardware and fresh OpenWrt not tested here.'
