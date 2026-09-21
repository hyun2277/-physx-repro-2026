"""Read-only source/wheel inspection; writes a sanitized build result, no imports."""
import datetime
import argparse
import email.parser
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
LOG = ROOT / 'logs/official-example-20260921/flash-attention-build'
SOURCE = ROOT / 'sources/flash-attention-060c9188beec'
BUILD = ROOT / 'build/flash-attention-060c9188beec'
WHEELS = ROOT / 'cache/wheels/flash-attention'


def digest(stream):
    value = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        value.update(block)
    return value.hexdigest()


def file_digest(path):
    with path.open('rb') as stream:
        return digest(stream)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    output = args.output_dir or LOG
    assert output.is_absolute() and output.resolve().is_relative_to(ROOT / 'logs/official-example-20260921')
    if args.output_dir:
        output.mkdir(parents=False, exist_ok=False)
    for name in ('wheel-METADATA.txt', 'wheel-WHEEL.txt', 'result.json'):
        assert not (output / name).exists(), 'Existing inspection record must not be overwritten.'
    expected = json.loads((LOG / 'source-files.json').read_text())
    changed = {'fetched_source': [], 'build_copy_original_files': []}
    for label, root in [('fetched_source', SOURCE), ('build_copy_original_files', BUILD)]:
        for entry in expected:
            path = root / entry['path']
            if 'symlink' in entry:
                match = path.is_symlink() and str(path.readlink()) == entry['symlink']
            else:
                match = path.is_file() and not path.is_symlink() and file_digest(path) == entry['sha256']
            if not match:
                changed[label].append(entry['path'])
    wheels = list(WHEELS.glob('*.whl'))
    assert len(wheels) == 1, 'Expected exactly one completed wheel.'
    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as package:
        names = package.namelist()
        metadata_name, = [name for name in names if name.endswith('.dist-info/METADATA')]
        wheel_metadata_name, = [name for name in names if name.endswith('.dist-info/WHEEL')]
        metadata_text = package.read(metadata_name).decode()
        wheel_text = package.read(wheel_metadata_name).decode()
        metadata = email.parser.Parser().parsestr(metadata_text)
        assert metadata['Name'].replace('_', '-').lower() == 'flash-attn'
        assert metadata['Version'] == '2.8.3'
        binaries = []
        for name in names:
            if name.endswith('.so'):
                with package.open(name) as stream:
                    binaries.append({'path': name, 'size': package.getinfo(name).file_size, 'sha256': digest(stream)})
        assert len(binaries) == 1 and binaries[0]['path'].startswith('flash_attn_2_cuda.')
    attempts = []
    for path in sorted((ROOT / 'logs/official-example-20260921/runs').glob('*flash-attention-wheel*/status.json')):
        state = json.loads(path.read_text())
        attempts.append({'run': str(path.parent), **state})
    assert attempts and attempts[-1]['phase'] == 'completed' and attempts[-1]['command_exit_code'] == 0
    result = {'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'source_commit': '060c9188beec3a8b62b33a3bfa6d5d2d44975fab',
              'wheel': str(wheel), 'wheel_size': wheel.stat().st_size, 'wheel_sha256': file_digest(wheel),
              'distribution': metadata['Name'], 'version': metadata['Version'],
              'requires_dist': metadata.get_all('Requires-Dist', []), 'wheel_metadata': wheel_text,
              'binaries': binaries, 'source_changes': changed,
              'fetched_source_preserved': not changed['fetched_source'],
              'original_build_source_unmodified': not changed['build_copy_original_files'],
              'source_patches': [], 'attempts': attempts,
              'build_only': True, 'installed_by_this_task': False, 'gpu_executed_by_this_task': False,
              'runtime_compatibility_proven': False}
    with (output / 'wheel-METADATA.txt').open('x') as stream:
        stream.write(metadata_text)
    with (output / 'wheel-WHEEL.txt').open('x') as stream:
        stream.write(wheel_text)
    with (output / 'result.json').open('x') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    assert not any(changed.values()), 'Source changes need review.'


if __name__ == '__main__':
    main()
