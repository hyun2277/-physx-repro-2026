"""Offline exact-wheel installation, complete dependency and before/after checks."""
import datetime
import hashlib
import importlib.metadata as md
import json
import pathlib
import subprocess
import sys
import zipfile
from email.parser import Parser

ROOT = pathlib.Path('/home/minsujo/Desktop/SH/PHYSx')
SITE = ROOT / 'envs/physxgen/lib/python3.10/site-packages'
sys.path.insert(0, str(SITE))
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
BASE = ROOT / 'logs/official-example-20260921'
PIP = ROOT / 'logs/python-foundation-install-20260921/pip_without_site.py'

def dump(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')

def inventory():
    return {canonicalize_name(d.metadata['Name']): d.version for d in md.distributions(path=[str(SITE)])}

def main():
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory = BASE / 'wheel-installs' / stamp
    directory.mkdir(parents=True)
    before = inventory()
    dump(directory / 'before.json', before)
    assert before['torch'] == '2.7.1+cu128' and before['torchvision'] == '0.22.1+cu128'
    wanted, records = {}, []
    for argument in sys.argv[1:]:
        file = pathlib.Path(argument).resolve()
        assert file.is_relative_to(ROOT) and file.suffix == '.whl'
        with zipfile.ZipFile(file) as archive:
            names = [n for n in archive.namelist() if n.endswith('.dist-info/METADATA')]
            assert len(names) == 1
            metadata = Parser().parsestr(archive.read(names[0]).decode())
            assert not any(n.endswith('.pth') or n.endswith('/sitecustomize.py') for n in archive.namelist())
        name = canonicalize_name(metadata['Name'])
        assert name not in wanted and name not in before, f'Refusing replacement or repeat install: {name}'
        wanted[name] = metadata['Version']
        records.append({'name': name, 'version': metadata['Version'], 'path': str(file),
                        'bytes': file.stat().st_size, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest(),
                        'requires_dist': metadata.get_all('Requires-Dist', [])})
    combined = {**before, **wanted}
    for record in records:
        for text in record['requires_dist']:
            requirement = Requirement(text)
            if requirement.marker and not requirement.marker.evaluate({'extra': ''}):
                continue
            name = canonicalize_name(requirement.name)
            assert name in combined and requirement.specifier.contains(combined[name]), f'Unsatisfied {text}'
    dump(directory / 'verified-wheels.json', records)
    lock = directory / 'wheels.lock.txt'
    lock.write_text(''.join(f"{r['name']} @ {pathlib.Path(r['path']).as_uri()} --hash=sha256:{r['sha256']}\n" for r in records))

    def command(label, args):
        place = directory / label
        place.mkdir()
        argv = [sys.executable, '-I', '-B', '-S', str(PIP)] + args
        result = {'argv': argv, 'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        dump(place / 'command.json', result)
        with (place / 'stdout.log').open('wb') as out, (place / 'stderr.log').open('wb') as err:
            process = subprocess.run(argv, stdout=out, stderr=err)
        result.update(exit_code=process.returncode, ended_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        dump(place / 'result.json', result)
        print(json.dumps({'step': label, 'exit_code': process.returncode, 'log': str(place)}), flush=True)
        if process.returncode:
            print((place / 'stderr.log').read_text()[-4000:], flush=True)
            raise SystemExit(process.returncode)

    flags = ['install', '--no-index', '--no-deps', '--no-compile', '--only-binary=:all:', '--require-hashes', '-r', str(lock)]
    report = directory / 'preview.json'
    command('dry-run', flags + ['--dry-run', '--report', str(report)])
    preview = json.loads(report.read_text())
    selected = {canonicalize_name(x['metadata']['name']): x['metadata']['version'] for x in preview['install']}
    assert selected == wanted, f'Preview differs: {selected} != {wanted}'
    for item in preview['install']:
        name = canonicalize_name(item['metadata']['name'])
        original = next(r for r in records if r['name'] == name)
        assert item['download_info']['archive_info']['hashes']['sha256'] == original['sha256']
    command('install', flags)
    after = inventory()
    dump(directory / 'after.json', after)
    assert after == combined, 'Unexpected distribution version change'
    command('pip-check', ['check'])
    dump(directory / 'result.json', {'success': True, 'installed': wanted, 'preserved_existing': len(before), 'logs': str(directory)})
    print(json.dumps({'success': True, 'installed': wanted, 'logs': str(directory)}), flush=True)

if __name__ == '__main__':
    main()
