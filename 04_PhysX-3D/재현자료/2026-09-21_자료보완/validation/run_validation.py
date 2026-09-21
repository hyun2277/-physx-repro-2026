"""Run only the fixed, non-GPU material checks with per-execution logs."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
BASE = ROOT / 'repro-records/04_PhysX-3D/재현자료/2026-09-21_자료보완'
LOG = ROOT / 'logs/repro-materials-20260921'
PY = ['/usr/bin/python3', '-I', '-B', '-S']
commands = {
    'verify-materials': PY + [str(BASE / 'verify_materials.py')],
    'static-audit': PY + [str(LOG / 'check_materials_static.py')],
    'gpu-plan': [str(ROOT / 'envs/physxgen/bin/python'), '-I', '-B', '-S', str(BASE / 'gpu/gpu_check_launcher.py'), '--plan'],
    'gpu-plan-mock-tests': PY + [str(BASE / 'gpu/test_preparation.py'), '-v'],
}
name = sys.argv[1]
argv = commands[name]
start = datetime.datetime.now().astimezone()
run = LOG / (name + '-' + start.strftime('%Y%m%dT%H%M%S%f') + '-' + uuid.uuid4().hex[:6])
run.mkdir(mode=0o700)
environment = {'PATH': '/usr/bin:/bin', 'HOME': '/home/minsujo', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'TMPDIR': str(ROOT / 'tmp')}
command = {'argv': argv, 'cwd': str(ROOT), 'started_at': start.isoformat(),
           'scope': 'read-only validation, static inspection, nonexecuting GPU plan, or pure mock tests only'}
(run / 'command.json').write_text(json.dumps(command, ensure_ascii=False, indent=2) + '\n')
with (run / 'stdout.log').open('w') as out, (run / 'stderr.log').open('w') as err:
    process = subprocess.run(argv, cwd=ROOT, env=environment, stdin=subprocess.DEVNULL, stdout=out, stderr=err, check=False)
end = datetime.datetime.now().astimezone()
result = {'name': name, 'started_at': start.isoformat(), 'ended_at': end.isoformat(),
          'elapsed_seconds': (end-start).total_seconds(), 'exit_code': process.returncode,
          'log_directory': str(run), 'gpu_execution': False, 'installation': False}
(run / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
(LOG / ('latest-' + name + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(result, ensure_ascii=False, indent=2))
print((run / 'stdout.log').read_text())
print((run / 'stderr.log').read_text(), file=sys.stderr)
raise SystemExit(process.returncode)
