"""Record GPU selection, then dispatch the already reviewed launcher once."""
import csv
import datetime
import hashlib
import json
import os
from pathlib import Path
import resource
import stat
import subprocess
import sys

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
BASE = ROOT / 'logs/gpu-basic-check-20260921'
BUNDLE = ROOT / 'repro-records/04_PhysX-3D/재현자료/2026-09-21_자료보완'
LAUNCHER = BUNDLE / 'gpu/gpu_check_launcher.py'
ENV = {'HOME': '/home/minsujo', 'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
       'LC_ALL': 'C.UTF-8', 'TMPDIR': str(ROOT / 'tmp')}


def now():
    return datetime.datetime.now().astimezone().isoformat()


def write(name, value):
    (BASE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def command(name, argv):
    # No automatic retries; preserve one stdout/stderr and actual process exit.
    run = BASE / name
    run.mkdir(mode=0o700, exist_ok=False)
    started = now()
    record = {'argv': argv, 'cwd': str(ROOT), 'started_at': started,
              'attempt': 1, 'automatic_retry': False}
    (run / 'command.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    with (run / 'stdout.log').open('w') as out, (run / 'stderr.log').open('w') as err:
        process = subprocess.run(argv, cwd=ROOT, env=ENV, stdin=subprocess.DEVNULL,
                                 stdout=out, stderr=err, check=False)
    record.update(ended_at=now(), exit_code=process.returncode,
                  signal=-process.returncode if process.returncode < 0 else None)
    (run / 'result.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'step': name, 'exit_code': process.returncode, 'log_directory': str(run)}), flush=True)
    if process.returncode:
        raise RuntimeError(name + ' failed; stop without retry or protection changes.')
    return (run / 'stdout.log').read_text()


def verify_sources():
    entries = {item['path']: item for item in json.loads((BUNDLE / 'materials-manifest.json').read_text())['files']}
    result = {}
    for relative in ['gpu/gpu_check_launcher.py', 'gpu/pytorch_smoke_check.py']:
        raw = (BUNDLE / relative).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != entries[relative]['sha256']:
            raise RuntimeError('Prepared source differs from its reviewed manifest.')
        result[relative] = digest
    return result


def inventory():
    if (BASE / 'inventory-attempt.json').exists():
        raise RuntimeError('An inventory attempt is already recorded; no automatic retry.')
    write('inventory-attempt.json', {'started_at': now(), 'attempt': 1})
    sources = verify_sources()
    text = command('inventory-gpus', ['/usr/bin/nvidia-smi',
        '--query-gpu=index,uuid,pci.bus_id,name,driver_version,memory.total,memory.used,utilization.gpu,temperature.gpu,power.draw',
        '--format=csv,noheader,nounits'])
    columns = ['index', 'uuid', 'pci_bus_id', 'name', 'driver_version', 'memory_total_mib',
               'memory_used_mib', 'utilization_gpu_percent', 'temperature_c', 'power_w']
    gpus = []
    for row in csv.reader(text.splitlines()):
        if not row:
            continue
        if len(row) != len(columns):
            raise RuntimeError('Unexpected GPU inventory format.')
        gpu = dict(zip(columns, [field.strip() for field in row]))
        for key in ['index', 'memory_total_mib', 'memory_used_mib', 'utilization_gpu_percent']:
            gpu[key] = int(gpu[key])
        gpus.append(gpu)
    if len(gpus) != 2 or len({gpu['uuid'] for gpu in gpus}) != 2:
        raise RuntimeError('Expected exactly two uniquely identified GPUs; stop.')
    text = command('inventory-compute-apps', ['/usr/bin/nvidia-smi',
        '--query-compute-apps=gpu_uuid,pid,used_gpu_memory', '--format=csv,noheader,nounits'])
    applications = []
    for row in csv.reader(text.splitlines()):
        if not row:
            continue
        if len(row) != 3:
            raise RuntimeError('Unexpected compute-app query format.')
        applications.append(dict(zip(['gpu_uuid', 'pid', 'used_gpu_memory_mib'], [field.strip() for field in row])))
    known = {gpu['uuid'] for gpu in gpus}
    if any(app['gpu_uuid'] not in known or not app['pid'].isdigit() for app in applications):
        raise RuntimeError('Compute application identity is incomplete; stop.')
    mapping = {}
    for path in sorted(Path('/proc/driver/nvidia/gpus').glob('*/information')):
        fields = {}
        for line in path.read_text().splitlines():
            key, sep, value = line.partition(':')
            if sep:
                fields[key.strip()] = value.strip()
        gpu_uuid = fields.get('GPU UUID')
        if gpu_uuid not in known:
            continue
        if gpu_uuid in mapping or not fields.get('Device Minor', '').isdigit():
            raise RuntimeError('Ambiguous or missing UUID/device minor mapping.')
        minor = int(fields['Device Minor'])
        node = Path('/dev/nvidia' + str(minor))
        info = node.lstat()
        if not stat.S_ISCHR(info.st_mode) or os.minor(info.st_rdev) != minor:
            raise RuntimeError('Driver metadata and GPU character device disagree.')
        mapping[gpu_uuid] = {'device_minor': minor, 'device_node': str(node),
                             'driver_metadata_path': str(path),
                             'driver_bus_location': fields.get('Bus Location'),
                             'character_device_major': os.major(info.st_rdev)}
    if set(mapping) != known:
        raise RuntimeError('Not all inventory UUIDs map to driver device nodes.')
    occupied = {app['gpu_uuid'] for app in applications}
    eligible = [gpu for gpu in gpus if gpu['uuid'] not in occupied and gpu['utilization_gpu_percent'] == 0]
    decision = {'recorded_at': now(), 'gpus': gpus, 'compute_applications': applications,
                'uuid_device_mapping': mapping, 'prepared_source_sha256': sources,
                'selection_rule': 'No reported compute process and zero sampled utilization; prefer lower memory usage, then index.',
                'limit': 'A current snapshot is not an exclusive reservation; the launcher rechecks the selected GPU before the operation.'}
    if not eligible:
        decision.update(status='stopped', reason='Both GPUs have compute applications or no idle candidate can be confirmed.', selected=None)
    else:
        selected = min(eligible, key=lambda gpu: (gpu['memory_used_mib'], gpu['index']))
        decision.update(status='selected', selected={**selected, **mapping[selected['uuid']]})
    write('selection.json', decision)
    print(json.dumps(decision, ensure_ascii=False, indent=2), flush=True)


def execute():
    if (BASE / 'execution-attempt.json').exists():
        raise RuntimeError('GPU execution was already attempted; no retry allowed.')
    selected_record = json.loads((BASE / 'selection.json').read_text())
    if selected_record.get('status') != 'selected':
        raise RuntimeError('No idle GPU was selected; execution prohibited.')
    sources = verify_sources()
    selected = selected_record['selected']
    write('execution-attempt.json', {'started_at': now(), 'attempt': 1,
          'prepared_source_sha256': sources, 'selected': selected,
          'authorization': 'User authorized one basic PyTorch GPU check; no installation/build/download/paper experiment or retry.'})
    before = {p.name for p in (ROOT / 'logs/gpu-checks').glob('*')} if (ROOT / 'logs/gpu-checks').exists() else set()
    try:
        command('launcher-once', [str(ROOT / 'envs/physxgen/bin/python'), '-I', '-B', '-S',
                str(LAUNCHER), '--execute', '--gpu-uuid', selected['uuid'],
                '--device-minor', str(selected['device_minor'])])
    finally:
        runs = sorted(str(p) for p in (ROOT / 'logs/gpu-checks').glob('*') if p.name not in before)
        write('launcher-run-directories.json', {'recorded_at': now(), 'directories': runs})


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.umask(0o077)
    if len(sys.argv) != 2 or sys.argv[1] not in ('inventory', 'execute'):
        raise SystemExit('Use inventory or execute.')
    phase = sys.argv[1]
    try:
        (inventory if phase == 'inventory' else execute)()
        return 0
    except Exception as error:
        failure = {'recorded_at': now(), 'phase': phase, 'error_type': type(error).__name__,
                   'message': str(error), 'retry_performed': False, 'protections_weakened': False}
        write(phase + '-failure.json', failure)
        print(json.dumps(failure, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
