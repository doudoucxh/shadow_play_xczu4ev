#!/usr/bin/env python3
"""Verify every delivery file and reject unexpected missing or changed files."""
import hashlib
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
failed = []
count = 0
for line in (root / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
    expected, relative = line.split('  ', 1)
    path = root / relative
    count += 1
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        failed.append(relative)
if failed:
    print('FAILED: '+', '.join(failed))
    sys.exit(1)
print('OK: '+str(count)+' release files verified.')
