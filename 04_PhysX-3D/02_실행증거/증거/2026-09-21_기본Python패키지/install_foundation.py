"""Hash-locked wheel-only foundation installation. No build/model/GPU imports."""
import datetime
from email.parser import BytesParser
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import traceback
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
PLAN = ROOT / 'logs/install-plan-20260921'
RUN = ROOT / 'logs/python-foundation-install-20260921'
ENV = ROOT / 'envs/physxgen'
SITE = ENV / 'lib/python3.10/site-packages'
WHEELS = ROOT / 'cache/python-foundation-wheels-20260921'
sys.path.insert(0, str(SITE))
from pip._vendor.packaging.markers import default_environment
from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.specifiers import SpecifierSet
from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename
from pip._vendor.packaging.version import Version

STATE = {'phase': 'starting', 'installation_started': False}
EXCLUDED = {'flash-attn', 'xformers', 'clip', 'utils3d', 'nvdiffrast', 'diffoctreerast',
            'diff-gaussian-rasterization', 'vox2seq', 'spconv-cu126', 'cumm-cu126'}


def now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()


def save(name, value):
    (RUN / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def stage(name, **values):
    STATE.update(phase=name, timestamp=now(), **values)
    save('status.json', STATE)
    print(now(), name, flush=True)


def command(name, argv):
    stage(name)
    entry = {'argv': [str(x) for x in argv], 'started': now()}
    save(name + '.command.json', entry)
    with (RUN / (name + '.stdout.log')).open('w') as out, (RUN / (name + '.stderr.log')).open('w') as err:
        result = subprocess.run(argv, cwd=ROOT, stdout=out, stderr=err, check=False)
    entry.update(finished=now(), exit_code=result.returncode)
    save(name + '.command.json', entry)
    if result.returncode:
        raise RuntimeError(f'{name} failed with exit {result.returncode}; see stdout/stderr logs')


def distributions():
    rows = list(importlib.metadata.distributions(path=[str(SITE)]))
    result = {canonicalize_name(d.metadata['Name']): d.version for d in rows}
    assert len(rows) == len(result), 'Duplicate installed distributions'
    return result


def read_lock():
    items = {}
    constraints = {}
    for raw in (PLAN / 'python-resolved.constraints.txt').read_text().splitlines():
        if raw.strip() and not raw.lstrip().startswith('#'):
            req = Requirement(raw)
            constraints[canonicalize_name(req.name)] = str(req.specifier)
    for raw in (PLAN / 'python-foundation.lock.txt').read_text().splitlines():
        if not raw.strip() or raw.startswith('#'):
            continue
        match = re.fullmatch(r'(\S+) @ (https://\S+) --hash=sha256:([a-f0-9]{64})', raw)
        assert match, 'Lock entry is not a single hash-locked HTTPS wheel'
        name, url, digest = match.groups()
        name = canonicalize_name(name)
        assert name not in items and name not in EXCLUDED
        parsed = urlsplit(url)
        assert not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
        assert parsed.hostname in {'files.pythonhosted.org', 'download.pytorch.org', 'download-r2.pytorch.org',
                                   'pypi.nvidia.com', 'nvidia-kaolin.s3.us-east-2.amazonaws.com'}
        filename = Path(unquote(parsed.path)).name
        wheel_name, version, build, tags = parse_wheel_filename(filename)
        assert canonicalize_name(wheel_name) == name and tags.intersection(set(sys_tags()))
        assert str(Version(str(version))) == str(version)
        assert str(version) in SpecifierSet(constraints[name])
        items[name] = {'name': name, 'version': str(version), 'url': url, 'sha256': digest, 'filename': filename}
    assert len(items) == 169
    assert items['torch']['version'] == '2.7.1+cu128'
    assert items['torchvision']['version'] == '0.22.1+cu128'
    return items


def dependencies(metadata, versions):
    issues = []
    active = 0
    marker_env = default_environment()
    marker_env['extra'] = ''
    for name, value in metadata.items():
        python = value.get('requires_python')
        if python and Version(platform.python_version()) not in SpecifierSet(python):
            issues.append({'package': name, 'requires_python': python})
        for raw in value.get('requires_dist', []):
            req = Requirement(raw)
            if req.marker is not None and not req.marker.evaluate(marker_env):
                continue
            active += 1
            dep = canonicalize_name(req.name)
            if req.url:
                issues.append({'package': name, 'requirement': raw, 'issue': 'direct URL dependency forbidden'})
            elif dep not in versions:
                issues.append({'package': name, 'requirement': raw, 'issue': 'missing from fixed set'})
            elif req.specifier and Version(versions[dep]) not in req.specifier:
                issues.append({'package': name, 'requirement': raw, 'found': versions[dep]})
            if req.extras:
                issues.append({'package': name, 'requirement': raw, 'issue': 'dependency extras require explicit review'})
    return {'active_requirement_count': active, 'issues': issues}


def check_report(report, expected, lock):
    got = {canonicalize_name(row['metadata']['name']): row['metadata']['version'] for row in report['install']}
    comparison = {'matches_versions': got == expected, 'count': len(report['install']),
                  'added': sorted(set(got) - set(expected)), 'missing': sorted(set(expected) - set(got)),
                  'changed': {k: {'expected': expected[k], 'actual': got[k]} for k in set(got) & set(expected) if got[k] != expected[k]}}
    for row in report['install']:
        name = canonicalize_name(row['metadata']['name'])
        info = row['download_info']
        assert info['url'] == (WHEELS / lock[name]['filename']).as_uri(), f'Non-local or different artifact: {name}'
        assert info['archive_info']['hashes']['sha256'] == lock[name]['sha256'], f'Different artifact hash: {name}'
    return comparison


def main():
    assert sys.flags.isolated and sys.flags.no_site and not sys.flags.optimize
    assert Path(sys.prefix) == ENV and os.environ.get('PHYSX_ROOT') == str(ROOT)
    assert os.environ.get('CUDA_VISIBLE_DEVICES') == '' and not list(Path('/dev').glob('nvidia*'))
    for p in ('/usr/local', '/home/minsujo/anaconda3', '/home/minsujo', '/etc', '/proc/sys'):
        assert os.statvfs(p).f_flag & os.ST_RDONLY, p
    before = json.loads((RUN / 'before.json').read_text())
    for name, digest in before['input_sha256'].items():
        assert sha(PLAN / name) == digest, f'Reviewed input changed: {name}'
    old = {canonicalize_name(d['name']): d['version'] for d in before['python_distributions']}
    assert distributions() == old
    command('isolation-check', [ENV / 'bin/python', '-I', '-B', '-S', PLAN / 'isolation_probe.py'])
    lock = read_lock()
    save('approved-wheels.json', list(lock.values()))
    expected = {k: v['version'] for k, v in lock.items()}
    baseline = {}
    for report_name in ('pip-dry-run-initial-report.json', 'pip-utils3d-dry-run-report.json'):
        for row in json.loads((PLAN / report_name).read_text())['install']:
            name = canonicalize_name(row['metadata']['name'])
            if name in lock:
                assert row['metadata']['version'] == expected[name]
                baseline[name] = row['metadata']
    assert set(baseline) == set(lock)
    checks = dependencies(baseline, expected | {'pip': old['pip']})
    save('baseline-dependencies.json', checks)
    assert not checks['issues'], 'Baseline dependencies differ or need review; stopped before downloads/install'
    WHEELS.mkdir(mode=0o700)
    pip = [ENV / 'bin/python', '-I', '-B', '-S', RUN / 'pip_without_site.py', '--isolated',
           '--disable-pip-version-check', '--no-input', '--keyring-provider', 'disabled',
           '--no-color', '--cache-dir', ROOT / 'cache/pip']
    binary = ['--no-index', '--only-binary=:all:', '--require-hashes', '--progress-bar', 'off']
    command('download-wheels', pip + ['download'] + binary + ['--dest', WHEELS, '-r', PLAN / 'python-foundation.lock.txt'])
    stage('checking-downloaded-wheels')
    assert {p.name for p in WHEELS.iterdir()} == {v['filename'] for v in lock.values()}, 'Wheel file set differs from fixed list'
    metadata = {}
    startup = {}
    for name, item in lock.items():
        path = WHEELS / item['filename']
        assert path.resolve().is_relative_to(WHEELS) and sha(path) == item['sha256'], f'Wheel hash mismatch: {name}'
        with zipfile.ZipFile(path) as archive:
            members = archive.namelist()
            paths = [m for m in members if m.endswith('.dist-info/METADATA') and len(Path(m).parts) == 2]
            assert len(paths) == 1
            data = BytesParser().parsebytes(archive.read(paths[0]))
            assert canonicalize_name(data['Name']) == name and data['Version'] == item['version']
            metadata[name] = {'name': data['Name'], 'version': data['Version'],
                              'requires_python': data.get('Requires-Python'), 'requires_dist': data.get_all('Requires-Dist', [])}
            normalize = lambda requirements: sorted(str(Requirement(x)) for x in requirements)
            assert normalize(metadata[name]['requires_dist']) == normalize(baseline[name].get('requires_dist', [])), f'Dependency metadata differs: {name}'
            startup[name] = [m for m in members if m.endswith('.pth') or Path(m).name in ('sitecustomize.py', 'usercustomize.py')]
    save('wheel-metadata.json', metadata)
    save('wheel-startup-files-not-executed.json', {k: v for k, v in startup.items() if v})
    check = dependencies(metadata, expected | {'pip': old['pip']})
    save('downloaded-dependencies.json', check)
    assert not check['issues'], 'Actual wheel dependencies differ; stopped before installation'
    local_lock = RUN / 'foundation.local.lock.txt'
    local_lock.write_text(''.join(f'{name} @ {(WHEELS / item["filename"]).as_uri()} --hash=sha256:{item["sha256"]}\n' for name, item in sorted(lock.items())))
    dry_report = RUN / 'offline-preview.json'
    command('offline-preview', pip + ['install', '--dry-run', '--ignore-installed', '--no-compile'] + binary + ['--report', dry_report, '-r', local_lock])
    comparison = check_report(json.loads(dry_report.read_text()), expected, lock)
    save('offline-preview-comparison.json', comparison)
    assert comparison['matches_versions'] and comparison['count'] == 169, 'Preview differs from fixed list'
    assert distributions() == old, 'Environment changed during preparation'
    for name, digest in before['input_sha256'].items():
        assert sha(PLAN / name) == digest, f'Reviewed input changed during preparation: {name}'
    stage('169-wheels-approved')
    STATE['installation_started'] = True
    command('install-foundation', pip + ['install', '--no-compile'] + binary + ['--report', RUN / 'install-report.json', '-r', local_lock])
    after = distributions()
    expected_after = old | expected
    version_check = {'expected_count': len(expected_after), 'actual_count': len(after),
                     'matches': after == expected_after, 'versions': after,
                     'changed_existing': {k: {'before': old[k], 'after': after.get(k)} for k in old if old[k] != after.get(k)}}
    save('installed-versions.json', version_check)
    assert version_check['matches'], 'Installed versions do not match fixed set'
    assert not (set(after) & EXCLUDED)
    assert after['torch'] == '2.7.1+cu128' and after['torchvision'] == '0.22.1+cu128'
    command('pip-check', pip + ['check'])
    stage('completed', exit_code=0, foundation_package_count=169, total_distribution_count=len(after),
          torch=after['torch'], torchvision=after['torchvision'], pip_check='passed')


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        stage('failed', error_type=type(error).__name__, error=str(error), exit_code=1)
        (RUN / 'failure.log').write_text(traceback.format_exc())
        print('Stopped without fallback, cleanup, or pin changes. See failure.log.', file=sys.stderr, flush=True)
        sys.exit(1)
