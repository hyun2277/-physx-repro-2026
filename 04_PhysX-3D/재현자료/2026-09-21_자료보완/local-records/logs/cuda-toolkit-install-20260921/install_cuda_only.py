"""Authorized CUDA-only install: compare, freeze exact artifacts, install, inspect.

Run only through the reviewed workspace_isolation.py. No source compilation,
Python package installation, model download, or GPU operation is performed.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback
from urllib.parse import urlsplit

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
PLAN = ROOT / 'logs/install-plan-20260921'
RUN = ROOT / 'logs/cuda-toolkit-install-20260921'
PREFIX = ROOT / 'toolchains/cuda-12.8.1'
CONDA = '/home/minsujo/anaconda3/condabin/conda'
PYTHON = ROOT / 'envs/physxgen/bin/python'
STATE = {'phase': 'starting', 'installation_started': False}


def now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()


def save(name, data):
    (RUN / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def stage(phase, **details):
    STATE.update(phase=phase, timestamp=now(), **details)
    save('status.json', STATE)
    print(f'{now()} {phase}', flush=True)


def command(label, argv):
    stage(label)
    info = {'argv': [str(x) for x in argv], 'started': now()}
    save(label + '.command.json', info)
    with (RUN / (label + '.stdout.log')).open('w') as out, (RUN / (label + '.stderr.log')).open('w') as err:
        result = subprocess.run(argv, cwd=ROOT, stdout=out, stderr=err, check=False)
    info.update(finished=now(), exit_code=result.returncode)
    save(label + '.command.json', info)
    if result.returncode:
        raise RuntimeError(f'{label} failed with exit code {result.returncode}; see its stdout/stderr logs')
    return (RUN / (label + '.stdout.log')).read_text()


def identity(record):
    return record['name'], record['version'], record.get('build_string', record.get('build'))


def artifact_records(report):
    """Recover all LINK artifact records without any new dependency resolution."""
    fetched = {identity(r): r for r in report['actions'].get('FETCH', [])}
    records = []
    for link in report['actions']['LINK']:
        key = identity(link)
        if key in fetched:
            record = fetched[key]
            origin = 'FETCH'
        else:
            path = ROOT / 'cache/conda' / link['dist_name'] / 'info/repodata_record.json'
            assert path.resolve().is_relative_to(ROOT / 'cache/conda'), str(path)
            record = json.loads(path.read_text())
            origin = 'workspace package cache metadata'
        assert identity(record) == key, f'Artifact identity mismatch: {key}'
        url = record['url']
        parsed = urlsplit(url)
        assert parsed.scheme == 'https' and not parsed.username and not parsed.password
        assert not parsed.query and not parsed.fragment
        expected_url = link['base_url'].rstrip('/') + '/' + link['platform'] + '/' + record['fn']
        assert url == expected_url, f'Artifact channel/platform mismatch: {key}'
        assert link['base_url'] in (
            'https://conda.anaconda.org/nvidia/label/cuda-12.8.1',
            'https://repo.anaconda.com/pkgs/main',
        ), f'Unexpected channel: {key}'
        assert re.fullmatch(r'[0-9a-f]{32}', record['md5'])
        assert re.fullmatch(r'[0-9a-f]{64}', record['sha256'])
        records.append({'name': key[0], 'version': key[1], 'build': key[2],
                        'url': url, 'md5': record['md5'], 'sha256': record['sha256'],
                        'metadata_origin': origin})
    assert len(records) == len({r['name'] for r in records}) == 118
    return sorted(records, key=lambda r: r['name'])


def validate_files():
    """Check real files and link targets; do not compile, import CUDA, or load a GPU."""
    records = [json.loads(p.read_text()) for p in (PREFIX / 'conda-meta').glob('*.json')]
    paths = sorted({name for r in records for name in r.get('files', [])})
    requirements = {
        'nvcc': ['nvcc'], 'ptxas': ['ptxas'], 'nvlink': ['nvlink'], 'cudafe': ['cudafe++'],
        'cuda_driver_header': ['cuda.h'], 'cuda_runtime_header': ['cuda_runtime.h'],
        'cuda_runtime_api_header': ['cuda_runtime_api.h'], 'host_config_header': ['host_config.h'],
        'nvvm_compiler': ['cicc'], 'libdevice': ['libdevice.10.bc'],
        'nvvm_library': ['libnvvm.so'], 'cudart_library': ['libcudart.so'],
        'cublas_header': ['cublas_v2.h'], 'cublas_library': ['libcublas.so'],
        'cublas_lt_library': ['libcublasLt.so'],
    }
    result = {}
    for group, basenames in requirements.items():
        candidates = [PREFIX / name for name in paths if any(
            Path(name).name == basename or (basename.endswith('.so') and Path(name).name.startswith(basename + '.'))
            for basename in basenames)]
        if group == 'nvcc':
            candidates = [PREFIX / 'bin/nvcc'] + [p for p in candidates if p != PREFIX / 'bin/nvcc']
        found = []
        for path in candidates:
            target = path.resolve(strict=True)
            assert target.is_relative_to(PREFIX), f'External file/link target: {path} -> {target}'
            assert target.is_file() and target.stat().st_size > 0, f'Missing/empty file: {path}'
            executable = os.access(path, os.X_OK)
            if group in ('nvcc', 'ptxas', 'nvlink', 'cudafe', 'nvvm_compiler'):
                assert executable, f'Not executable: {path}'
            found.append({'path': str(path), 'resolved_path': str(target),
                          'bytes': target.stat().st_size, 'is_symlink': path.is_symlink(),
                          'executable': executable})
        assert found, f'No actual file for requirement: {group}'
        result[group] = found
    save('actual-files.json', result)
    output = command('nvcc-version', [PREFIX / 'bin/nvcc', '--version'])
    assert 'V12.8.93' in output and 'release 12.8' in output, 'Unexpected NVCC version'
    return result


def main():
    assert os.environ.get('PHYSX_ROOT') == str(ROOT), 'Reviewed isolation is required'
    assert os.environ.get('CUDA_VISIBLE_DEVICES') == ''
    assert not list(Path('/dev').glob('nvidia*')), 'GPU devices must not be exposed'
    for path in ('/usr/local', '/home/minsujo/anaconda3', '/home/minsujo', '/etc', '/proc/sys'):
        assert os.statvfs(path).f_flag & os.ST_RDONLY, f'External mount is not read-only: {path}'
    assert not os.path.lexists(PREFIX), 'Existing target: stop without deletion or overwrite'
    before = json.loads((RUN / 'before.json').read_text())
    for name, expected in before['input_sha256'].items():
        assert hashlib.sha256((PLAN / name).read_bytes()).hexdigest() == expected, f'Reviewed input changed: {name}'
    command('isolation-check', [PYTHON, '-I', '-B', '-S', PLAN / 'isolation_probe.py'])
    baseline = json.loads((PLAN / 'conda-final-isolated-preview.json').read_text())
    expected = {identity(r) for r in baseline['actions']['LINK']}
    specs = {tuple(line.strip().split('=', 2)) for line in (PLAN / 'cuda-toolkit.conda-specs.txt').read_text().splitlines() if line.strip() and not line.lstrip().startswith('#')}
    assert len(expected) == 118 and specs == expected
    baseline_artifacts = artifact_records(baseline)
    save('approved-artifacts.json', baseline_artifacts)
    common = [CONDA, 'create', '--prefix', str(PREFIX), '--override-channels',
              '--strict-channel-priority', '--repodata-fn', 'repodata.json',
              '--no-default-packages', '--copy', '--yes',
              '-c', 'https://conda.anaconda.org/nvidia/label/cuda-12.8.1',
              '-c', 'https://repo.anaconda.com/pkgs/main']
    fresh = json.loads(command('fresh-preview', common + ['--dry-run', '--json', '--file', str(PLAN / 'cuda-toolkit.conda-specs.txt')]))
    actual = {identity(r) for r in fresh.get('actions', {}).get('LINK', [])}
    diff = {'removed': sorted(expected - actual), 'added_or_changed': sorted(actual - expected),
            'link_count': len(fresh.get('actions', {}).get('LINK', [])),
            'unlink_count': len(fresh.get('actions', {}).get('UNLINK', [])),
            'success': fresh.get('success'), 'dry_run': fresh.get('dry_run'),
            'prefix': fresh.get('prefix'), 'action_prefix': fresh.get('actions', {}).get('PREFIX')}
    save('fresh-preview-comparison.json', diff)
    assert fresh.get('success') is True and fresh.get('dry_run') is True
    assert fresh.get('prefix') == fresh['actions'].get('PREFIX') == str(PREFIX)
    assert actual == expected and diff['link_count'] == 118 and not diff['unlink_count'], 'Package composition changed: installation stopped'
    fresh_artifacts = artifact_records(fresh)
    compare_keys = ('name', 'version', 'build', 'url', 'md5', 'sha256')
    artifact_changes = [{'before': a, 'after': b} for a, b in zip(baseline_artifacts, fresh_artifacts) if any(a[k] != b[k] for k in compare_keys)]
    save('artifact-comparison.json', {'count': len(fresh_artifacts), 'changes': artifact_changes})
    assert not artifact_changes, 'Package URL/hash changed: installation stopped'
    explicit = RUN / 'cuda-toolkit.explicit.txt'
    explicit.write_text('@EXPLICIT\n' + ''.join(r['url'] + '#' + r['md5'] + '\n' for r in fresh_artifacts))
    save('install-artifacts-sha256.json', fresh_artifacts)
    assert not os.path.lexists(PREFIX), 'Target appeared after preview: stop'
    stage('exact-artifacts-approved', package_count=118)
    STATE['installation_started'] = True
    # Conda23.3.1 @EXPLICIT parses URL#MD5, performs no dependency solve, and
    # honors --copy. SHA256 values are separately preserved above.
    command('cuda-install', common + ['--file', str(explicit)])
    installed = [json.loads(p.read_text()) for p in (PREFIX / 'conda-meta').glob('*.json')]
    got = {identity(r) for r in installed}
    post = {'count': len(installed), 'removed_or_missing': sorted(expected - got),
            'added_or_changed': sorted(got - expected), 'matches_preview': got == expected and len(installed) == 118}
    save('installed-package-comparison.json', post)
    assert post['matches_preview'], 'Installed package composition mismatch'
    stage('checking-actual-files')
    files = validate_files()
    stage('completed', package_count=118, nvcc_version='12.8.93', actual_file_groups=len(files), exit_code=0)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        stage('failed', error_type=type(error).__name__, error=str(error), exit_code=1)
        (RUN / 'failure.log').write_text(traceback.format_exc())
        print(f'Stopped; see {RUN}/failure.log. Isolation unchanged; no cleanup or retry.', file=sys.stderr, flush=True)
        sys.exit(1)
