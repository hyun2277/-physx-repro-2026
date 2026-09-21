"""Read-only checks for the new reproduction archive; no archived code execution."""
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
REPO = ROOT / 'repro-records'
BASE = REPO / '04_PhysX-3D/재현자료/2026-09-21_자료보완'
inventory = json.loads((ROOT / 'logs/repro-materials-20260921/copied-materials.json').read_text())
issues = []
for record in inventory['files']:
    original = (ROOT / record['source_relative_to_PHYSx']).read_bytes()
    copied = (BASE / record['path']).read_bytes()
    if original != copied or hashlib.sha256(copied).hexdigest() != record['sha256']:
        issues.append({'copy': record['path']})
python_files = sorted(BASE.rglob('*.py'))
for path in python_files:
    ast.parse(path.read_text(), filename=str(path))
for path in BASE.rglob('*.md'):
    for link in re.findall(r'\]\(([^)]+)\)', path.read_text()):
        if link.startswith(('https:', 'http:', '/', '#')):
            continue
        target = link.split('#')[0]
        if target and not (path.parent / target).exists():
            issues.append({'broken_link': str(path.relative_to(BASE)), 'target': target})
for path in BASE.rglob('*'):
    if not path.is_file():
        continue
    raw = path.read_bytes()
    if b'\0' in raw or len(raw) > 2_100_000:
        issues.append({'unexpected_binary_or_size': str(path.relative_to(BASE))})
    for pattern in (rb'(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{20,}',
                    rb'-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY',
                    rb'https?://[^\s/"<>]+:[^\s/@"<>]+@'):
        if re.search(pattern, raw):
            issues.append({'credential_pattern_path_only': str(path.relative_to(BASE))})
    if path.suffix == '.json':
        json.loads(raw)
plan = BASE / 'local-records/logs/install-plan-20260921'
historical = json.loads((plan / 'isolation-review-sha256.json').read_text())
for name, digest in historical.items():
    if hashlib.sha256((plan / name).read_bytes()).hexdigest() != digest:
        issues.append({'isolation_review_mismatch': name})
for phase, expected in [('python-foundation-install-20260921', 7), ('cuda-toolkit-install-20260921', 9)]:
    before = json.loads((BASE / 'local-records/logs' / phase / 'before.json').read_text())
    hashes = before['input_sha256']
    assert len(hashes) == expected
    for name, digest in hashes.items():
        if hashlib.sha256((plan / name).read_bytes()).hexdigest() != digest:
            issues.append({'runner_input_mismatch': phase, 'name': name})
raw = subprocess.check_output(['/usr/bin/git', '-c', 'core.quotePath=false', 'status', '--porcelain=v1', '-z', '--untracked-files=all'], cwd=REPO)
changed = [item[3:].decode() for item in raw.split(b'\0') if item]
for path in changed:
    if not path.startswith('04_PhysX-3D/'):
        issues.append({'out_of_scope_change': path})
result = {'pass': not issues, 'copied_files_equal_originals': len(inventory['files']),
          'parsed_python_files': len(python_files), 'isolation_review_hashes': len(historical),
          'foundation_input_hashes': 7, 'cuda_input_hashes': 9,
          'changed_files_in_04': len(changed), 'issues': issues,
          'limit': 'Static files, source hashes and Git path inspection only; no installer, package import, bwrap, NVIDIA tool, or GPU execution.'}
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['pass'] else 1)
