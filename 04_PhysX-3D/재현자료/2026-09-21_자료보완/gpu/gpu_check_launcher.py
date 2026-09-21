"""Prepare, or explicitly execute, one selected-GPU PyTorch compatibility check.

Default/--plan uses only the standard library and emits a plan. It does not
launch subprocesses, import torch, query NVIDIA tools, or open GPU devices.
--execute is for a separately authorized future GPU check, not installation.
"""
import argparse
import csv
import datetime
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys
import time
import uuid


ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
ENV = ROOT / 'envs/physxgen'
TOOLKIT = ROOT / 'toolchains/cuda-12.8.1'
HERE = Path(__file__).resolve().parent
SMOKE = HERE / 'pytorch_smoke_check.py'
UUID_RE = re.compile(r'GPU-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
SMOKE_TIMEOUT_SECONDS = 90
QUERY_TIMEOUT_SECONDS = 15
DRIVER_QUERY_FIELDS = 'uuid,name,driver_version,memory.total,memory.used,utilization.gpu,temperature.gpu,power.draw'
USAGE_QUERY_FIELDS = 'timestamp,uuid,memory.total,memory.used,utilization.gpu,temperature.gpu,power.draw'
MINIMAL_ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}


class CheckStopped(Exception):
    pass


def require(condition, message):
    if not condition:
        raise CheckStopped(message)


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def selected_nodes(minor):
    require(type(minor) is int and 0 <= minor < 128, 'GPU device minor must be an integer from 0 to 127.')
    return [f'/dev/nvidia{minor}', '/dev/nvidiactl', '/dev/nvidia-uvm']


def environment(gpu_uuid, temp_dir):
    """Allowlist; HOME is preserved, credentials/loader overrides are omitted."""
    env = {
        'HOME': os.environ.get('HOME') or pwd.getpwuid(os.getuid()).pw_dir,
        'PATH': f'{ENV}/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
        'PHYSX_ROOT': str(ROOT), 'PHYSX_GPU_CHECK_ISOLATED': '1',
        'CUDA_VISIBLE_DEVICES': gpu_uuid, 'CUDA_DEVICE_ORDER': 'PCI_BUS_ID',
        'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
        'TMPDIR': str(temp_dir), 'TMP': str(temp_dir), 'TEMP': str(temp_dir),
        'XDG_CACHE_HOME': str(ROOT / 'cache/gpu-check/xdg'),
        'XDG_CONFIG_HOME': str(ROOT / 'cache/gpu-check/xdg-config'),
        'XDG_DATA_HOME': str(ROOT / 'cache/gpu-check/xdg-data'),
        'XDG_STATE_HOME': str(ROOT / 'cache/gpu-check/xdg-state'),
        'XDG_RUNTIME_DIR': str(temp_dir / 'runtime'),
        'TORCH_HOME': str(ROOT / 'cache/torch'),
        'TORCH_EXTENSIONS_DIR': str(ROOT / 'build/torch-extensions'),
        'HF_HOME': str(ROOT / 'cache/gpu-check/huggingface'),
        'HF_HUB_CACHE': str(ROOT / 'cache/gpu-check/huggingface/hub'),
        'HF_MODULES_CACHE': str(ROOT / 'cache/gpu-check/huggingface/modules'),
        'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
        'CUDA_CACHE_PATH': str(ROOT / 'cache/gpu-check/cuda'),
        'TRITON_CACHE_DIR': str(ROOT / 'cache/gpu-check/triton'),
        'NUMBA_CACHE_DIR': str(ROOT / 'cache/gpu-check/numba'),
        'MPLCONFIGDIR': str(ROOT / 'cache/gpu-check/matplotlib'),
        'PYTHONPYCACHEPREFIX': str(ROOT / 'cache/gpu-check/pycache'),
        'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
    }
    # Deliberately no LD_LIBRARY_PATH, CUDA_HOME, toolkit/stubs, compiler flags,
    # HF_TOKEN, Git/SSH credentials, proxy, DBUS, SSH_AUTH_SOCK, or inherited env.
    return env


def bwrap_command(command, gpu_uuid, minor, temp_dir):
    argv = [
        '/usr/bin/bwrap', '--die-with-parent', '--new-session',
        '--unshare-user', '--unshare-pid', '--unshare-ipc', '--unshare-uts', '--unshare-net',
        '--cap-drop', 'ALL', '--clearenv', '--ro-bind', '/', '/',
        '--bind', str(ROOT), str(ROOT),
        '--ro-bind', str(ENV), str(ENV), '--ro-bind', str(TOOLKIT), str(TOOLKIT),
        '--bind', str(temp_dir), '/tmp', '--bind', str(temp_dir), '/var/tmp',
        '--proc', '/proc', '--ro-bind', '/proc/sys', '/proc/sys',
        '--dev', '/dev', '--bind', str(temp_dir / 'shm'), '/dev/shm',
        '--chdir', str(ROOT),
    ]
    for node in selected_nodes(minor):
        argv += ['--dev-bind', node, node]
    for key, value in environment(gpu_uuid, temp_dir).items():
        argv += ['--setenv', key, value]
    return argv + ['--'] + [str(part) for part in command]


def smoke_command(gpu_uuid, minor):
    return [str(ENV / 'bin/python'), '-I', '-B', '-S', str(SMOKE), '--execute',
            '--gpu-uuid', gpu_uuid, '--device-minor', str(minor)]


def plan(gpu_uuid=None, minor=None):
    if gpu_uuid is not None:
        require(UUID_RE.fullmatch(gpu_uuid) is not None, 'A complete GPU UUID is required; prefixes and ordinal selectors are rejected.')
    if minor is not None:
        selected_nodes(minor)
    chosen_uuid = gpu_uuid or '<FULL_GPU_UUID>'
    chosen_minor = minor if minor is not None else '<DEVICE_MINOR>'
    result = {
        'mode': 'plan', 'executed': False, 'future_authorization_required': True,
        'gpu_uuid': gpu_uuid, 'device_minor': minor,
        'future_command': [str(ENV / 'bin/python'), '-I', '-B', '-S', str(HERE / 'gpu_check_launcher.py'),
                           '--execute', '--gpu-uuid', chosen_uuid, '--device-minor', str(chosen_minor)],
        'python': str(ENV / 'bin/python'), 'expected_torch': '2.7.1+cu128',
        'expected_torchvision': '0.22.1+cu128', 'expected_compute_capability': [12, 0],
        'numeric_check': 'one 256x256 float32 matrix multiplication; result entries must equal 256',
        'smoke_timeout_seconds': SMOKE_TIMEOUT_SECONDS, 'sampler_sleep_seconds': 1,
        'sampler_interval': 'query duration plus nominal 1-second sleep; exact start/finish times in each command JSON',
        'driver_query_fields': DRIVER_QUERY_FIELDS.split(','),
        'usage_query_fields': USAGE_QUERY_FIELDS.split(','),
        'usage_samples': 'before smoke, during smoke, and after successful smoke',
        'logs_parent': str(ROOT / 'logs/gpu-checks'),
        'identity_guard': 'execute-only /proc/driver/nvidia/gpus/*/information UUID and Device Minor mapping',
        'required_device_nodes': selected_nodes(minor) if minor is not None else ['/dev/nvidia<DEVICE_MINOR>', '/dev/nvidiactl', '/dev/nvidia-uvm'],
        'network': 'separate network namespace; no downloads',
        'prohibited': ['installation', 'extension compilation', 'model download', 'model inference',
                       'training', 'modprobe', 'sudo', 'driver reset', 'automatic escalation'],
        'limit': 'Device-node filtering and CUDA visibility are not a hard multi-tenant GPU isolation boundary; control/UVM nodes are shared.',
        'hardware_execution_validated': False,
    }
    if gpu_uuid is not None and minor is not None:
        result['planned_smoke_argv'] = bwrap_command(smoke_command(gpu_uuid, minor), gpu_uuid, minor, ROOT / 'tmp/gpu-check-<RUN_ID>')
    return result


def within_workspace(path):
    require(path.resolve().is_relative_to(ROOT), 'Path resolves outside the workspace: ' + str(path))
    return path


def verify_mapping(gpu_uuid, minor):
    """Read driver text only; no device opening or nvidia-smi fallback."""
    matches = []
    for path in sorted(Path('/proc/driver/nvidia/gpus').glob('*/information')):
        fields = {}
        for line in path.read_text().splitlines():
            key, separator, value = line.partition(':')
            if separator:
                fields[key.strip()] = value.strip()
        if fields.get('GPU UUID', '').lower() == gpu_uuid.lower():
            matches.append((path, fields))
    require(len(matches) == 1, 'Full GPU UUID has no unique driver-proc mapping; stopped without GPU queries.')
    path, fields = matches[0]
    require(fields.get('Device Minor', '').isdigit() and int(fields['Device Minor']) == minor,
            'Selected UUID does not map to the requested GPU device minor.')
    for node in selected_nodes(minor):
        target = Path(node)
        require(target.exists() and not target.is_symlink(), 'Required GPU node missing or symlinked: ' + node)
        data = target.stat()
        require(stat.S_ISCHR(data.st_mode), 'Required GPU path is not a character device: ' + node)
        if node == f'/dev/nvidia{minor}':
            require(os.minor(data.st_rdev) == minor, 'GPU node minor disagrees with driver metadata.')
    return {'gpu_uuid': gpu_uuid, 'device_minor': minor, 'driver_metadata_path': str(path),
            'device_nodes': selected_nodes(minor)}


def write_json(path, value):
    within_workspace(path)
    require(not path.is_symlink(), 'Log path may not be a symlink.')
    path.write_text(json.dumps(value, indent=2) + '\n')


def failed_child_record(record, *, process_started, exit_code, error_name, terminated=False):
    """Pure bookkeeping: a later sampler failure must not rewrite smoke success."""
    updated = dict(record)
    if not process_started:
        updated.update(exit_code=None, launch_error=error_name, finished=utc())
    else:
        updated['exit_code'] = exit_code
        updated.setdefault('finished', utc())
        if terminated:
            updated.update(interrupted=True, terminated=True)
    return updated


def execute(gpu_uuid, minor):
    # All subprocess and GPU-related activity is below this explicit boundary.
    import resource
    import subprocess

    require(gpu_uuid is not None and minor is not None, '--execute requires both the full GPU UUID and device minor.')
    plan(gpu_uuid, minor)
    require(sys.flags.isolated and sys.flags.no_site, 'Use the designated Python with -I -B -S.')
    require(ROOT.resolve() == ROOT, 'Workspace root is not canonical.')
    require(Path(sys.prefix).resolve() == ENV, 'Use envs/physxgen/bin/python for the launcher.')
    for path in (ENV, TOOLKIT, HERE, SMOKE):
        require(path.exists(), 'Required path missing: ' + str(path))
        within_workspace(path)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.umask(0o077)
    run_id = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:12]
    run = within_workspace(ROOT / 'logs/gpu-checks' / run_id)
    temp_dir = within_workspace(ROOT / 'tmp' / ('gpu-check-' + run_id))
    run.mkdir(parents=True, mode=0o700, exist_ok=False)
    temp_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    state = {'run_id': run_id, 'gpu_uuid': gpu_uuid, 'device_minor': minor,
             'started': utc(), 'phase': 'preflight', 'smoke_process_started': False,
             'smoke_exit_code': None, 'smoke_passed': False}
    process = None
    child_record = None

    def status(phase, **fields):
        state.update(phase=phase, **fields)
        write_json(run / 'status.json', state)

    def record_command(name, argv, timeout):
        record = {'argv': argv, 'started': utc(), 'timeout_seconds': timeout}
        write_json(run / (name + '.command.json'), record)
        with (run / (name + '.stdout.log')).open('w') as out, (run / (name + '.stderr.log')).open('w') as err:
            try:
                result = subprocess.run(argv, env=MINIMAL_ENV, cwd=ROOT, stdin=subprocess.DEVNULL,
                                        stdout=out, stderr=err, timeout=timeout, check=False)
                record.update(exit_code=result.returncode, timed_out=False)
            except subprocess.TimeoutExpired:
                record.update(exit_code=None, timed_out=True)
                write_json(run / (name + '.command.json'), dict(record, finished=utc()))
                raise CheckStopped(name + ' timed out; no retry or isolation fallback.') from None
            except BaseException as error:
                record.update(exit_code=None, launch_or_wait_error=type(error).__name__)
                write_json(run / (name + '.command.json'), dict(record, finished=utc()))
                raise
        write_json(run / (name + '.command.json'), dict(record, finished=utc()))
        require(record['exit_code'] == 0, name + ' failed; inspect its stdout/stderr logs.')
        return (run / (name + '.stdout.log')).read_text()

    def gpu_query(name, fields, compute=False):
        option = '--query-compute-apps=' if compute else '--query-gpu='
        command = ['/usr/bin/nvidia-smi', '--id=' + gpu_uuid, option + fields, '--format=csv,noheader,nounits']
        return record_command(name, bwrap_command(command, gpu_uuid, minor, temp_dir), QUERY_TIMEOUT_SECONDS)

    try:
        status('preflight')
        mapping = verify_mapping(gpu_uuid, minor)
        write_json(run / 'device-mapping.json', mapping)
        for value in environment(gpu_uuid, temp_dir).values():
            if value.startswith(str(ROOT) + '/') and ':' not in value:
                path = Path(value)
                if path not in (ROOT,):
                    within_workspace(path).mkdir(parents=True, exist_ok=True, mode=0o700)
        (temp_dir / 'shm').mkdir(mode=0o700, exist_ok=False)
        # This is the first driver-query command, and already uses the GPU namespace.
        info = gpu_query('driver-info', DRIVER_QUERY_FIELDS)
        rows = list(csv.reader(line for line in info.splitlines() if line.strip()))
        require(len(rows) == 1 and rows[0][0].strip().lower() == gpu_uuid.lower(), 'Driver query did not report exactly the selected UUID.')
        applications = gpu_query('existing-compute-apps', 'pid,gpu_uuid', compute=True)
        require(not applications.strip(), 'Existing compute applications were reported; no smoke check started.')
        gpu_query('usage-before', USAGE_QUERY_FIELDS)
        argv = bwrap_command(smoke_command(gpu_uuid, minor), gpu_uuid, minor, temp_dir)
        child_record = {'argv': argv, 'started': utc(), 'timeout_seconds': SMOKE_TIMEOUT_SECONDS,
                        'process_started': False}
        write_json(run / 'smoke.command.json', child_record)
        status('smoke_launching')
        with (run / 'smoke.stdout.log').open('w') as out, (run / 'smoke.stderr.log').open('w') as err:
            process = subprocess.Popen(argv, cwd=ROOT, env=MINIMAL_ENV, stdin=subprocess.DEVNULL,
                                       stdout=out, stderr=err, start_new_session=True)
            child_record.update(process_started=True, process_started_at=utc())
            write_json(run / 'smoke.command.json', child_record)
            # Popen success is process launch evidence, not proof of a CUDA call.
            status('smoke_running', smoke_process_started=True)
            deadline = time.monotonic() + SMOKE_TIMEOUT_SECONDS
            sample = 0
            while process.poll() is None:
                require(time.monotonic() < deadline, 'Smoke check exceeded its time budget.')
                gpu_query(f'usage-{sample:04d}', USAGE_QUERY_FIELDS)
                sample += 1
                if process.poll() is None:
                    time.sleep(1)
            child_record.update(exit_code=process.returncode, finished=utc(), sampler_count=sample)
            write_json(run / 'smoke.command.json', child_record)
            status('smoke_finished', smoke_exit_code=process.returncode, smoke_passed=process.returncode == 0)
            require(process.returncode == 0, 'Smoke check failed; see smoke stdout/stderr.')
        status('usage_final')
        gpu_query('usage-final', USAGE_QUERY_FIELDS)
        status('completed', finished=utc(), exit_code=0, claim='Only the bounded PyTorch/torchvision GPU smoke check passed.')
        print(json.dumps({'status': 'completed', 'logs': str(run), 'gpu_uuid': gpu_uuid, 'exit_code': 0}, indent=2))
        return 0
    except BaseException as error:
        terminated = False
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            terminated = True
        if child_record is not None:
            child_record = failed_child_record(
                child_record, process_started=process is not None,
                exit_code=process.returncode if process is not None else None,
                error_name=type(error).__name__, terminated=terminated)
            write_json(run / 'smoke.command.json', child_record)
        reason = str(error) if isinstance(error, CheckStopped) else type(error).__name__
        status('stopped', finished=utc(), exit_code=1, reason=reason,
               failed_stage=state['phase'],
               smoke_exit_code=process.returncode if process is not None else None)
        print(json.dumps({'status': 'stopped', 'logs': str(run), 'reason': reason, 'exit_code': 1}, indent=2), file=sys.stderr)
        return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--plan', action='store_true', help='Default: JSON only; no subprocess/GPU access.')
    mode.add_argument('--execute', action='store_true', help='Future explicitly authorized GPU check only.')
    parser.add_argument('--gpu-uuid', help='Complete GPU-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx UUID; no index/prefix.')
    parser.add_argument('--device-minor', type=int, help='Driver Device Minor identifying /dev/nvidiaN, not an assumed CUDA ordinal.')
    args = parser.parse_args(argv)
    try:
        if args.execute:
            return execute(args.gpu_uuid, args.device_minor)
        print(json.dumps(plan(args.gpu_uuid, args.device_minor), indent=2))
        return 0
    except CheckStopped as error:
        print(json.dumps({'status': 'stopped', 'reason': str(error), 'exit_code': 1}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
