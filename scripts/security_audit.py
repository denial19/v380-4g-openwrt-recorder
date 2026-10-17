#!/usr/bin/env python3
"""Check publishable Git files and all existing reachable history for known secrets.

Does not print or upload secret values. Run on your OpenWrt checkout before a release:
  python3 scripts/security_audit.py

For GitHub Actions / external CI without private files:
  python3 scripts/security_audit.py --public-only

Limited to known credentials and common leak patterns; **manual review still required**.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

BLOCKED_NAMES = re.compile(
    r'(?:^|/)(?:archive|recordings|work|\.ssh)(?:/|$)|'
    r'(?:^|/)(?:id_ed25519|id_rsa|\.env)(?:$|\.)|'
    r'\.(?:mp4|h265|bin|pyc|log|pem|key)$|'
    r'(?:^|/)(?:v380_camera_password|v380_recorder\.json)$', re.I
)
IMEI = re.compile(rb'(?<![0-9])\d{15}(?![0-9])')
HARDCODED_ID = re.compile(rb'\bDEVICE_ID\s*=\s*\d{7,}\b')
BASIC_PASSWORD = re.compile(
    rb'(?im)^\s*(?:camera_)?password\s*=\s*[\x27\x22]'
    rb'(?!YOUR_|CHANGEME|EXAMPLE|<|\$)[^\x27\x22\n]{6,}[\x27\x22]'
)


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.DEVNULL)


def private_tokens() -> list[bytes]:
    vals = []
    p = Path('/etc/v380_camera_password')
    if p.is_file():
        v = p.read_bytes().strip()
        if len(v) >= 4:
            vals.append(v)
    cfg = Path('/etc/v380_recorder.json')
    if cfg.is_file():
        try:
            obj = json.loads(cfg.read_text())
            value = str(obj.get('device_id', ''))
            if value.isdigit() and len(value) >= 6:
                vals.append(value.encode())
        except (OSError, ValueError, TypeError):
            pass
    # For a working install predating the public config, read the local-only
    # source identifier; do not print or embed it anywhere.
    src = Path('/mnt/usb2/V380/relay_capture.py')
    if src.is_file():
        try:
            matches = re.findall(rb'(?m)^DEVICE_ID\s*=\s*(\d{6,})\s*$', src.read_bytes())
            vals.extend(matches)
        except OSError:
            pass
    return list(dict.fromkeys(vals))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument('--public-only', action='store_true', help='No local private file lookup (for CI)')
    args = ap.parse_args()
    repo = args.repo.resolve()
    try:
        git(repo, 'rev-parse', '--is-inside-work-tree')
    except subprocess.CalledProcessError:
        print('ERROR: not a Git repository', file=sys.stderr)
        return 2

    secrets = [] if args.public_only else private_tokens()
    if not args.public_only and not secrets:
        print('WARNING: no local private ID/password found; exact-token audit is incomplete')

    problems = set()
    seen = set()

    def check(name: str, blob: bytes, where: str) -> None:
        key = (name, blob)
        if key in seen:
            return
        seen.add(key)
        errors = []
        if BLOCKED_NAMES.search(name):
            errors.append('forbidden filename')
        if len(blob) > 8 * 1024 * 1024:
            errors.append('file >8 MiB (manual review required)')
        elif b'\0' not in blob[:1024]:
            if IMEI.search(blob):
                errors.append('15-digit identifier pattern')
            if HARDCODED_ID.search(blob):
                errors.append('hard-coded device ID assignment')
            if name.startswith('src/') and BASIC_PASSWORD.search(blob):
                errors.append('possible hard-coded password')
            if any(value in blob for value in secrets):
                errors.append('matches a private local ID or credential')
        if errors:
            problems.add((name, where, ', '.join(errors)))

    # Read actual committed blobs, including past revisions.
    try:
        history = git(repo, 'rev-list', '--objects', '--all').splitlines()
        for item in history:
            oid, _, path = item.partition(b' ')
            if not path:
                continue
            sha = oid.decode('ascii')
            if git(repo, 'cat-file', '-t', sha).strip() != b'blob':
                continue
            name = path.decode('utf-8', 'replace')
            content = git(repo, 'cat-file', 'blob', sha)
            check(name, content, 'history')
    except subprocess.CalledProcessError:
        print('ERROR: unable to scan Git history', file=sys.stderr)
        return 2

    # Include staged changes and current worktree, even before git add.
    for raw in git(repo, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split(b'\0'):
        if not raw:
            continue
        name = raw.decode('utf-8', 'replace')
        p = repo/name
        if p.is_file():
            check(name, p.read_bytes(), 'worktree')
    # Git index may contain staged content that differs from working tree.
    for raw in git(repo, 'ls-files', '-z').split(b'\0'):
        if not raw:
            continue
        name = raw.decode('utf-8', 'replace')
        try:
            check(name, git(repo, 'show', ':'+name), 'index')
        except subprocess.CalledProcessError:
            problems.add((name, 'index', 'unable to scan index entry'))

    if problems:
        for name, where, reason in sorted(problems):
            print(f'BLOCK: {where}: {name}: {reason}')
        print('FAILED: fix leaks before publishing; past Git history may require rewriting.')
        return 1
    print('PASS: no recognized secret patterns in worktree, Git index or reachable history')
    print('NOTE: a heuristic scan cannot guarantee that all private data are absent.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
