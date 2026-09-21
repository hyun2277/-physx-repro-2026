"""Preserve the fetched pin; make and hash a separate offline build copy."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
SOURCE = ROOT / 'sources/flash-attention-060c9188beec'
BUILD = ROOT / 'build/flash-attention-060c9188beec'
LOG = ROOT / 'logs/official-example-20260921/flash-attention-build'
WHEELS = ROOT / 'cache/wheels/flash-attention'
PIN = '060c9188beec3a8b62b33a3bfa6d5d2d44975fab'


def snapshot(root):
    result = []
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if '.git' in relative.parts:
            continue
        if path.is_symlink():
            if not path.resolve().is_relative_to(root):
                raise RuntimeError('Source contains an external symlink.')
            result.append({'path': str(relative), 'symlink': str(path.readlink())})
        elif path.is_file():
            result.append({'path': str(relative), 'size': path.stat().st_size,
                           'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    return result


def main():
    assert SOURCE.is_dir() and not BUILD.exists() and not BUILD.is_symlink()
    metadata = json.loads((ROOT / 'logs/official-example-20260921/flash-attention-source.json').read_text())
    assert metadata['commit'] == PIN and metadata['path'] == str(SOURCE)
    assert (SOURCE / 'csrc/cutlass/include/cutlass/cutlass.h').is_file()
    assert (SOURCE / 'csrc/composable_kernel/example/ck_tile/01_fmha/generate.py').is_file()
    assert SOURCE.resolve() == SOURCE and BUILD.parent.resolve().is_relative_to(ROOT)
    LOG.mkdir(parents=True, exist_ok=False)
    WHEELS.mkdir(parents=True, exist_ok=True)
    assert not list(WHEELS.iterdir()), 'Wheel destination must initially be empty.'
    original = snapshot(SOURCE)
    shutil.copytree(SOURCE, BUILD, symlinks=True, ignore=shutil.ignore_patterns('.git'))
    copied = snapshot(BUILD)
    assert original == copied, 'Build copy does not exactly match source files.'
    (LOG / 'source-files.json').write_text(json.dumps(original, indent=2) + '\n')
    record = {'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'source': str(SOURCE), 'source_commit': PIN, 'build_copy': str(BUILD),
              'wheel_destination': str(WHEELS), 'source_file_count': len(original),
              'source_manifest_sha256': hashlib.sha256((LOG / 'source-files.json').read_bytes()).hexdigest(),
              'copy_matches_source': True, 'excluded': ['.git metadata only'],
              'patches': [], 'build_attempted': False, 'installed': False, 'gpu_executed': False}
    (LOG / 'preparation.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
