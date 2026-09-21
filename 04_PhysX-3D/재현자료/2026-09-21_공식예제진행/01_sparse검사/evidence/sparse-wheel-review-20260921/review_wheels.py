"""Download exactly two locked wheels and inspect bytes without importing them."""
import base64
import datetime
from email.parser import BytesParser
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import urllib.request
from urllib.parse import urlsplit
import zipfile

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
RUN = ROOT / 'logs/sparse-wheel-review-20260921'
CACHE = ROOT / 'cache/sparse-wheels'
PLAN = ROOT / 'logs/install-plan-20260921'
SITE = ROOT / 'envs/physxgen/lib/python3.10/site-packages'
SELF = RUN / 'review_wheels.py'
CUOBJDUMP = ROOT / 'toolchains/cuda-12.8.1/bin/cuobjdump'


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def save(name, value):
    (RUN / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def pins():
    result = []
    for line in (PLAN / 'python-sparse-candidate.lock.txt').read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r'(\S+) @ (https://\S+) --hash=sha256:([a-f0-9]{64})', line)
        assert match
        name, url, sha = match.groups()
        parsed = urlsplit(url)
        assert parsed.hostname == 'files.pythonhosted.org'
        assert not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
        result.append({'name': name, 'url': url, 'sha256': sha, 'filename': Path(parsed.path).name})
    assert {x['name'] for x in result} == {'spconv-cu126', 'cumm-cu126'}
    return result


def run_command(name, argv, allow_failure=False, compressed=False):
    info = {'argv': list(map(str, argv)), 'started': stamp(), 'timeout_seconds': 300,
            'stdout_encoding': 'gzip' if compressed else 'plain',
            'no_package_import_or_gpu_operation': True}
    save(name + '.command.json', info)
    outpath = RUN / (name + ('.stdout.log.gz' if compressed else '.stdout.log'))
    with outpath.open('wb') as out, (RUN / (name + '.stderr.log')).open('wb') as err:
        if compressed:
            # gzip is performed after collection so subprocess timeout bounds the
            # inspector independently of output streaming or parser behavior.
            temporary = RUN / (name + '.stdout.raw')
            with temporary.open('xb') as raw:
                try:
                    proc = subprocess.run(argv, cwd=ROOT, stdout=raw, stderr=err,
                                          stdin=subprocess.DEVNULL, timeout=300)
                    info.update(exit_code=proc.returncode, timed_out=False)
                except subprocess.TimeoutExpired:
                    info.update(exit_code=None, timed_out=True)
            with temporary.open('rb') as source, gzip.GzipFile(fileobj=out, mode='wb') as zipped:
                for block in iter(lambda: source.read(4 * 1024 * 1024), b''):
                    zipped.write(block)
            # Only this just-created raw duplicate is removed; gzip preserves stdout.
            temporary.unlink()
        else:
            try:
                proc = subprocess.run(argv, cwd=ROOT, stdout=out, stderr=err,
                                      stdin=subprocess.DEVNULL, timeout=300)
                info.update(exit_code=proc.returncode, timed_out=False)
            except subprocess.TimeoutExpired:
                info.update(exit_code=None, timed_out=True)
    info['finished'] = stamp()
    save(name + '.command.json', info)
    if not allow_failure:
        assert info.get('exit_code') == 0 and not info.get('timed_out'), name
    return info


def download(name):
    record = next(x for x in pins() if x['name'] == name)
    target = CACHE / record['filename']
    if target.exists():
        assert target.is_file() and not target.is_symlink() and digest(target) == record['sha256']
        print(json.dumps(dict(record, bytes=target.stat().st_size, reused_verified_file=True)))
        return
    partial = target.with_suffix('.whl.part')
    assert not partial.exists() and not partial.is_symlink()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(record['url'], timeout=90) as response, partial.open('xb') as output:
        assert response.status == 200
        assert urlsplit(response.url).hostname == 'files.pythonhosted.org'
        h = hashlib.sha256()
        size = 0
        while True:
            block = response.read(4 * 1024 * 1024)
            if not block:
                break
            output.write(block)
            h.update(block)
            size += len(block)
    assert h.hexdigest() == record['sha256'], 'Downloaded artifact hash mismatch'
    partial.rename(target)
    print(json.dumps(dict(record, bytes=size, reused_verified_file=False)))


def inspect_wheel(record):
    target = CACHE / record['filename']
    assert digest(target) == record['sha256']
    dest = CACHE / 'extracted' / record['name']
    assert not dest.exists()
    dest.mkdir(parents=True, mode=0o700)
    elf_paths = []
    with zipfile.ZipFile(target) as archive:
        members = archive.infolist()
        inventory = [{'path': i.filename, 'bytes': i.file_size, 'compressed_bytes': i.compress_size} for i in members]
        save(record['name'] + '.zip-inventory.json', inventory)
        metadata_paths = [i.filename for i in members if i.filename.endswith('.dist-info/METADATA')]
        assert len(metadata_paths) == 1
        metadata_bytes = archive.read(metadata_paths[0])
        metadata = BytesParser().parsebytes(metadata_bytes)
        row = dict(record, bytes=target.stat().st_size,
                   metadata_name=metadata['Name'], version=metadata['Version'],
                   requires_python=metadata.get('Requires-Python'),
                   requires_dist=metadata.get_all('Requires-Dist', []),
                   startup_files=[i.filename for i in members if i.filename.endswith('.pth') or PurePosixPath(i.filename).name in ('sitecustomize.py', 'usercustomize.py')])
        (RUN / (record['name'] + '.METADATA.txt')).write_bytes(metadata_bytes)
        for entry in members:
            path = PurePosixPath(entry.filename)
            assert not path.is_absolute() and '..' not in path.parts
            if entry.is_dir():
                continue
            # Extract only static inspection material, never import/install it.
            if not ('.so' in path.name or path.suffix == '.py' or '.dist-info/' in entry.filename):
                continue
            output = dest / entry.filename
            assert output.resolve().is_relative_to(dest)
            output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            data = archive.read(entry)
            output.write_bytes(data)
            if data.startswith(b'\x7fELF'):
                elf_paths.append(output)
        row['elf_files'] = [str(p.relative_to(CACHE)) for p in elf_paths]
        save(record['name'] + '.metadata.json', row)
    elf_results = []
    for index, path in enumerate(elf_paths):
        label = record['name'] + f'.elf-{index:02d}'
        run_command(label + '.dynamic', ['/usr/bin/readelf', '--wide', '--dynamic', str(path)])
        dynamic = (RUN / (label + '.dynamic.stdout.log')).read_text()
        library = dict(path=str(path), bytes=path.stat().st_size, sha256=digest(path),
                       needed=re.findall(r'\(NEEDED\).*?\[(.*?)\]', dynamic),
                       rpath=re.findall(r'\((?:RUNPATH|RPATH)\).*?\[(.*?)\]', dynamic))
        run_command(label + '.ptx-list', [str(CUOBJDUMP), '--list-ptx', str(path)], allow_failure=True)
        listing = (RUN / (label + '.ptx-list.stdout.log')).read_text()
        library['ptx_listing'] = listing.strip().splitlines()
        run_command(label + '.elf-list', [str(CUOBJDUMP), '--list-elf', str(path)], allow_failure=True)
        library['cubin_listing'] = (RUN / (label + '.elf-list.stdout.log')).read_text().strip().splitlines()
        if 'PTX file' in listing:
            result = run_command(label + '.ptx-dump', [str(CUOBJDUMP), '--dump-ptx', str(path)],
                                 allow_failure=True, compressed=True)
            versions, targets = set(), set()
            entries = 0
            with gzip.open(RUN / (label + '.ptx-dump.stdout.log.gz'), 'rt', errors='replace') as source:
                for line in source:
                    if line.lstrip().startswith('.version '): versions.add(line.strip())
                    if line.lstrip().startswith('.target '): targets.add(line.strip())
                    if re.search(r'\.entry\b', line): entries += 1
            library.update(ptx_versions=sorted(versions), ptx_targets=sorted(targets),
                           ptx_entry_line_count=entries, ptx_inspection_exit_code=result['exit_code'])
        elf_results.append(library)
    save(record['name'] + '.elf-summary.json', elf_results)
    return row


def main():
    assert sys.flags.isolated and sys.flags.no_site and not sys.flags.optimize
    assert os.environ.get('PHYSX_ROOT') == str(ROOT)
    assert os.environ.get('CUDA_VISIBLE_DEVICES') == '' and not list(Path('/dev').glob('nvidia*'))
    assert os.statvfs('/home/minsujo').f_flag & os.ST_RDONLY
    assert ROOT.resolve() == ROOT
    for path in (RUN, CACHE):
        assert path.resolve().is_relative_to(ROOT)
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.umask(0o077)
    if len(sys.argv) == 3 and sys.argv[1] == 'download':
        download(sys.argv[2])
        return
    assert len(sys.argv) == 1
    save('status.json', {'phase': 'starting', 'timestamp': stamp(), 'installed': False, 'gpu_executed': False})
    records = pins()
    save('locked-artifacts.json', records)
    current = {d.metadata['Name'].lower().replace('_', '-'): d.version for d in importlib.metadata.distributions(path=[str(SITE)])}
    save('installed-distributions-before.json', current)
    baseline = json.loads((PLAN / 'pip-dry-run-initial-report.json').read_text())
    baseline = {r['metadata']['name'].lower().replace('_', '-'): r['metadata'] for r in baseline['install']}
    rows = []
    for record in records:
        run_command('download-' + record['name'], [sys.executable, '-I', '-B', '-S', str(SELF), 'download', record['name']])
        row = inspect_wheel(record)
        base = baseline[record['name']]
        assert row['version'] == base['version']
        assert sorted(row['requires_dist']) == sorted(base.get('requires_dist', []))
        rows.append(row)
    save('dependency-metadata-comparison.json', {'matches_reviewed_baseline': True, 'packages': rows,
         'note': 'No resolver, package import, install, source build, NVRTC compilation, or GPU execution occurred.'})
    after = {d.metadata['Name'].lower().replace('_', '-'): d.version for d in importlib.metadata.distributions(path=[str(SITE)])}
    assert current == after
    save('preservation.json', {'python_distribution_versions_unchanged': True, 'distribution_count': len(after)})
    save('status.json', {'phase': 'completed', 'timestamp': stamp(), 'installed': False, 'gpu_executed': False,
                         'wheel_count': len(rows), 'metadata_matches_reviewed_baseline': True})
    print('Static wheel inspection completed; no install/import/build/GPU operation.')


if __name__ == '__main__':
    main()
