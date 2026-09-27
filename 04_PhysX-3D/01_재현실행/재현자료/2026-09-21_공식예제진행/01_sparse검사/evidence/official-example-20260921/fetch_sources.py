"""Fetch explicitly pinned public sources; run only through workspace isolation."""
import datetime
import json
import pathlib
import subprocess
import sys
import hashlib

ROOT = pathlib.Path('/home/minsujo/Desktop/SH/PHYSx')
TASK = ROOT / 'logs/official-example-20260921'
PINS = json.loads((ROOT / 'logs/install-plan-20260921/source-pins.json').read_text())
PINS['dinov2'] = {
    'url': 'https://github.com/facebookresearch/dinov2.git',
    'commit': '9c7e3245797cf7be5b5729445a4af1272bd610df',
    'reason': 'Official register-model release implementation; additional dependency was previously unpinned.',
}

def run(label, args, cwd):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    log = TASK / 'source-commands' / (stamp + '-' + label)
    log.mkdir(parents=True)
    meta = {'argv': args, 'cwd': str(cwd), 'started_at': stamp}
    (log / 'command.json').write_text(json.dumps(meta, indent=2) + '\n')
    with (log / 'stdout.log').open('wb') as out, (log / 'stderr.log').open('wb') as err:
        p = subprocess.run(args, cwd=cwd, stdout=out, stderr=err)
    meta.update(exit_code=p.returncode, finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (log / 'result.json').write_text(json.dumps(meta, indent=2) + '\n')
    print(json.dumps({'label': label, 'exit_code': p.returncode, 'log': str(log)}), flush=True)
    if p.returncode:
        print((log / 'stderr.log').read_text(errors='replace')[-4000:], flush=True)
        raise SystemExit(p.returncode)

def main():
    for name in sys.argv[1:]:
        pin = PINS[name]
        dest = ROOT / 'sources' / (name + '-' + pin['commit'][:12])
        if dest.exists():
            head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=dest, text=True).strip()
            status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=dest, text=True)
            if head != pin['commit'] or status:
                raise SystemExit(f'Existing checkout requires review: {dest}')
            print(f'Existing clean pinned checkout retained: {dest}', flush=True)
            continue
        dest.mkdir(parents=True)
        git = ['git', '-c', 'credential.helper=', '-c', 'core.hooksPath=/dev/null']
        run(name + '-init', git + ['init', '.'], dest)
        run(name + '-origin', git + ['remote', 'add', 'origin', pin['url']], dest)
        run(name + '-fetch', git + ['fetch', '--depth=1', 'origin', pin['commit']], dest)
        run(name + '-checkout', git + ['checkout', '--detach', pin['commit']], dest)
        if (dest / '.gitmodules').exists():
            run(name + '-submodules', git + ['submodule', 'update', '--init', '--recursive', '--depth=1'], dest)
        run(name + '-status', git + ['status', '--porcelain'], dest)
        run(name + '-submodule-status', git + ['submodule', 'status', '--recursive'], dest)
        (TASK / (name + '-source.json')).write_text(json.dumps({'path': str(dest), **pin}, indent=2) + '\n')

if __name__ == '__main__':
    main()
