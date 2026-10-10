"""Check staged backup data without printing credential values; no network I/O."""
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

MAX_BLOB_BYTES = 95 * 1024 * 1024
SECRET_PATTERNS = [
    ('private_key', re.compile(rb'-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----')),
    ('github_token', re.compile(rb'\bgh[pousr]_[A-Za-z0-9]{30,}\b|github_pat_[A-Za-z0-9_]{60,}')),
    ('aws_access_key', re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b')),
]


def inspect_blob(path, data):
    issues = []
    parts = Path(path).parts
    if any(part.lower() in ('.vm_access', '.ssh', '.aws', '.venv') for part in parts):
        issues.append('private_or_environment_path')
    filename = Path(path).name.lower()
    if filename.startswith('.env') and filename != '.env.example':
        issues.append('environment_credentials_file')
    if len(data) > MAX_BLOB_BYTES:
        issues.append('blob_exceeds_95_MiB')
    if path.lower().endswith('.docx'):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            data = b'\n'.join(archive.read(name) for name in archive.namelist() if name.endswith('.xml'))
    for name, pattern in SECRET_PATTERNS:
        if pattern.search(data):
            issues.append(name)
    return issues


def main():
    root = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip()
    changed = {p.decode('utf-8') for p in subprocess.check_output(
        ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMRT', '-z'], cwd=root).split(b'\0') if p}
    records = subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=root).split(b'\0')
    entries = []
    for record in records:
        if not record:
            continue
        meta, name = record.split(b'\t', 1)
        mode, sha, stage = meta.split()
        path = name.decode('utf-8')
        if path in changed:
            if mode == b'160000' or stage != b'0':
                raise ValueError('Unreviewed nested repository or unresolved index entry: '+path)
            entries.append((sha, path))
    failures = []
    total = 0
    with subprocess.Popen(['git', 'cat-file', '--batch'], cwd=root,
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE) as process:
        for sha, path in entries:
            process.stdin.write(sha+b'\n'); process.stdin.flush()
            header = process.stdout.readline().split()
            if len(header) != 3 or header[1] != b'blob':
                raise ValueError('Expected a staged blob: '+path)
            size = int(header[2]); data = process.stdout.read(size)
            if len(data) != size or process.stdout.read(1) != b'\n':
                raise ValueError('Incomplete staged blob: '+path)
            total += size
            issues = inspect_blob(path, data)
            if issues:
                failures.append({'path': path, 'issues': issues})
        process.stdin.close()
        process.wait()
        if process.returncode:
            raise RuntimeError('git cat-file failed')
    print(json.dumps({'staged_files_checked':len(entries),'staged_bytes_checked':total,
                      'failures':failures}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
