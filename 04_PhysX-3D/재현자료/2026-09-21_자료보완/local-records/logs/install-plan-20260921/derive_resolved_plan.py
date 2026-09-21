"""Offline transformation of successful dry-run reports into review artifacts."""
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

folder = Path(__file__).resolve().parent
root = folder.parents[1]
base = json.loads((folder / 'pip-dry-run-initial-report.json').read_text())
extra = json.loads((folder / 'pip-utils3d-dry-run-report.json').read_text())
items = {}
for report in (base, extra):
    for item in report['install']:
        name = canonicalize_name(item['metadata']['name'])
        if name in items:
            assert items[name]['metadata']['version'] == item['metadata']['version'], name
        items[name] = item
versions = {name: item['metadata']['version'] for name, item in items.items()}
versions['pip'] = '26.2.1'
issues = []
marker_env = dict(base['environment'], extra='')
for name, item in sorted(items.items()):
    for raw in item['metadata'].get('requires_dist', []):
        req = Requirement(raw)
        if req.marker is not None and not req.marker.evaluate(marker_env):
            continue
        dep = canonicalize_name(req.name)
        if dep not in versions:
            issues.append({'package': name, 'requirement': raw, 'issue': 'missing'})
        elif req.specifier and Version(versions[dep]) not in req.specifier:
            issues.append({'package': name, 'requirement': raw, 'found': versions[dep]})
assert not issues, issues

constraints = ['# Metadata-resolved candidates; no installation/build/GPU validation.']
foundation = ['# Exact Linux x86_64 / Python3.10 wheels; runtime validation remains pending.']
sparse = ['# Separate sparse candidates, pending RTX5090 operation validation.']
hash_evidence = []
for name, item in sorted(items.items()):
    constraints.append(name + '==' + item['metadata']['version'])
    download = item['download_info']
    url = download['url']
    parsed = urlsplit(url)
    assert parsed.username is None and parsed.password is None
    assert parsed.scheme == 'https' and parsed.hostname in {
        'files.pythonhosted.org', 'download.pytorch.org', 'download-r2.pytorch.org', 'pypi.nvidia.com',
        'nvidia-kaolin.s3.us-east-2.amazonaws.com',
    }, url
    sha = download.get('archive_info', {}).get('hashes', {}).get('sha256')
    if not sha:
        artifact = root / 'cache/pip' / Path(unquote(parsed.path)).name
        sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
        hash_evidence.append({'name': name, 'url': url, 'local_path': str(artifact), 'sha256': sha})
    assert len(sha) == 64
    line = f'{name} @ {url} --hash=sha256:{sha}'
    (sparse if name in {'spconv-cu126', 'cumm-cu126'} else foundation).append(line)

(folder / 'python-resolved.constraints.txt').write_text('\n'.join(constraints) + '\n')
(folder / 'python-foundation.lock.txt').write_text('\n'.join(foundation) + '\n')
(folder / 'python-sparse-candidate.lock.txt').write_text('\n'.join(sparse) + '\n')
(folder / 'supplemental-wheel-hashes.json').write_text(json.dumps(hash_evidence, indent=2) + '\n')
summary = {
    'base_report_packages': len(base['install']),
    'extra_report_packages': len(extra['install']),
    'combined_unique_packages': len(items),
    'foundation_packages': len(items) - 2,
    'sparse_candidate_packages': 2,
    'active_dependency_metadata_issues': issues,
    'validation_limit': 'Static dependency metadata with no optional extras. No installation, model imports, source builds, or GPU operations.',
}
(folder / 'python-metadata-validation.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
