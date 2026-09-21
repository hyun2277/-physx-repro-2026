"""Isolated, logged commands for the authorized single official PhysX example.

Default is --plan: no writes, subprocesses, NVIDIA queries, or torch import.
Run this controller with /usr/bin/python3 -I -B -S. --execute explicitly launches
one command. Profiles: download (network, read-only Python/Toolkit), install
(offline, writable Python), build (offline, read-only Python), gpu (offline,
read-only Python/Toolkit, one explicitly identified device). All non-GPU
profiles hide NVIDIA nodes. Compiler selection is set only for build/gpu.

This is a trusted-workload preservation boundary, not same-user adversarial
isolation: the host filesystem is readable, and NVIDIA control/UVM are shared.
Never use this logging runner for credentials or pass secrets in command args.
There is no automatic retry, device reset, modprobe, sudo, or weaker fallback.
"""
import argparse
import csv
import datetime
import hashlib
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
BASE = ROOT / 'logs/official-example-20260921'
PYENV = ROOT / 'envs/physxgen'
TOOLKIT = ROOT / 'toolchains/cuda-12.8.1'
PROFILES = ('download', 'install', 'build', 'gpu')
UUID_RE = re.compile(r'GPU-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
LABEL_RE = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}')
MINIMAL_ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}
GPU_FIELDS = 'index,uuid,pci.bus_id,name,driver_version,memory.total,memory.used,utilization.gpu,temperature.gpu,power.draw,timestamp'
QUERY_TIMEOUT = 15


class Stopped(Exception):
    pass


def require(condition, message):
    if not condition:
        raise Stopped(message)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def checked_path(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve().is_relative_to(ROOT), 'Path must resolve inside PHYSx.')
    return path


def gpu_nodes(minor):
    require(type(minor) is int and 0 <= minor < 128, 'Device minor must be an integer in [0,127].')
    return [f'/dev/nvidia{minor}', '/dev/nvidiactl', '/dev/nvidia-uvm']


def validate(args):
    require(args.profile in PROFILES, 'Unknown profile.')
    require(LABEL_RE.fullmatch(args.label) is not None, 'Use a short filename-safe label.')
    require(1 <= args.timeout_seconds <= 86400, 'Timeout must be between 1 and 86400 seconds.')
    checked_path(args.cwd)
    require(bool(args.command) and args.command[0].startswith('/'), 'Use an absolute command executable after --.')
    require(all('\x00' not in part for part in args.command), 'NUL in command argument.')
    # Logging is intentionally not suitable for auth commands or token arguments.
    for part in args.command:
        require(not re.search(r'(?i)(?:--(?:token|password|access-token|auth-token)(?:=|$)|authorization\s*:|https?://[^/\s]+@)', part),
                'Credential-bearing arguments are prohibited in this logging runner.')
    if args.profile == 'gpu':
        require(args.gpu_uuid is not None and UUID_RE.fullmatch(args.gpu_uuid), 'GPU profile needs a complete GPU UUID.')
        require(type(args.gpu_index) is int and 0 <= args.gpu_index < 128, 'GPU profile needs an explicit GPU index.')
        gpu_nodes(args.device_minor)
    else:
        require(args.gpu_uuid is None and args.gpu_index is None and args.device_minor is None,
                'GPU selectors are accepted only for the GPU profile.')


def environment(profile, gpu_uuid, temporary):
    """Fresh allowlist; do not forward tokens, proxy, loaders, or shell settings."""
    user = pwd.getpwuid(os.getuid())
    env = {
        'HOME': os.environ.get('HOME') or user.pw_dir, 'USER': user.pw_name, 'LOGNAME': user.pw_name,
        'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'TERM': 'dumb',
        'PATH': f'{PYENV}/bin:/usr/bin:/bin',
        'PHYSX_ROOT': str(ROOT), 'PHYSX_PYENV': str(PYENV), 'PHYSX_CUDA': str(TOOLKIT),
        'PHYSX_PLAN': str(ROOT / 'logs/install-plan-20260921'),
        'PHYSX_RUN_PROFILE': profile, 'PHYSX_WORKSPACE_ISOLATED': '1',
        'TMPDIR': str(temporary), 'TMP': str(temporary), 'TEMP': str(temporary),
        'XDG_RUNTIME_DIR': str(temporary / 'runtime'),
        'XDG_CACHE_HOME': str(ROOT / 'cache/xdg'),
        'XDG_CONFIG_HOME': str(ROOT / 'cache/xdg-config'),
        'XDG_DATA_HOME': str(ROOT / 'cache/xdg-data'),
        'XDG_STATE_HOME': str(ROOT / 'cache/xdg-state'),
        'PIP_CACHE_DIR': str(ROOT / 'cache/pip'), 'PIP_CONFIG_FILE': '/dev/null',
        'PIP_DISABLE_PIP_VERSION_CHECK': '1', 'PIP_NO_INPUT': '1',
        'CONDA_PKGS_DIRS': str(ROOT / 'cache/conda'), 'CONDA_ENVS_PATH': str(ROOT / 'envs'),
        'CONDARC': str(ROOT / 'logs/install-plan-20260921/preview.condarc'),
        'CONDA_AUTO_UPDATE_CONDA': 'false', 'CONDA_NOTIFY_OUTDATED_CONDA': 'false',
        'CONDA_REPORT_ERRORS': 'false',
        'TORCH_HOME': str(ROOT / 'cache/torch'),
        'TORCH_EXTENSIONS_DIR': str(ROOT / 'build/torch-extensions'),
        'HF_HOME': str(ROOT / 'cache/huggingface'),
        'HF_HUB_CACHE': str(ROOT / 'cache/huggingface/hub'),
        'HF_ASSETS_CACHE': str(ROOT / 'cache/huggingface/assets'),
        'HF_XET_CACHE': str(ROOT / 'cache/huggingface/xet'),
        'HF_MODULES_CACHE': str(ROOT / 'cache/huggingface/modules'),
        'HF_DATASETS_CACHE': str(ROOT / 'cache/huggingface/datasets'),
        'HF_TOKEN_PATH': '/dev/null', 'HF_HUB_DISABLE_IMPLICIT_TOKEN': '1',
        'HF_HUB_DISABLE_TELEMETRY': '1', 'DO_NOT_TRACK': '1',
        'U2NET_HOME': str(ROOT / 'cache/u2net'),
        'PHYSX_CLIP_DOWNLOAD_ROOT': str(ROOT / 'cache/clip'),
        'CUDA_CACHE_PATH': str(ROOT / 'cache/cuda'),
        'TRITON_CACHE_DIR': str(ROOT / 'cache/triton'),
        'TRITON_DUMP_DIR': str(ROOT / 'cache/triton-dump'),
        'TRITON_OVERRIDE_DIR': str(ROOT / 'cache/triton-override'),
        'NUMBA_CACHE_DIR': str(ROOT / 'cache/numba'),
        'MPLCONFIGDIR': str(ROOT / 'cache/matplotlib'),
        'IMAGEIO_USERDIR': str(ROOT / 'cache/imageio'),
        'PYTHONPYCACHEPREFIX': str(ROOT / 'cache/pycache'),
        'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
        'CUDA_VISIBLE_DEVICES': gpu_uuid if profile == 'gpu' else '',
        'CUDA_DEVICE_ORDER': 'PCI_BUS_ID', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
        'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
        'GIT_CONFIG_COUNT': '2', 'GIT_CONFIG_KEY_0': 'core.hooksPath', 'GIT_CONFIG_VALUE_0': '/dev/null',
        'GIT_CONFIG_KEY_1': 'credential.helper', 'GIT_CONFIG_VALUE_1': '',
        'GIT_TEMPLATE_DIR': str(ROOT / 'cache/git-template-empty'),
        'GIT_TERMINAL_PROMPT': '0', 'GIT_ASKPASS': '/usr/bin/false', 'GIT_SSH_COMMAND': '/usr/bin/false',
    }
    if profile != 'download':
        env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_DATASETS_OFFLINE='1', PIP_NO_INDEX='1')
    if profile in ('build', 'gpu'):
        env.update({
            'PATH': f'{PYENV}/bin:{TOOLKIT}/bin:/usr/bin:/bin',
            'CUDA_HOME': str(TOOLKIT), 'CUDACXX': str(TOOLKIT / 'bin/nvcc'),
            'CC': '/usr/bin/gcc-13', 'CXX': '/usr/bin/g++-13',
            'CUDAHOSTCXX': '/usr/bin/g++-13', 'NVCC_CCBIN': '/usr/bin/g++-13',
            # NVIDIA Conda headers/libs live under targets/. PyTorch also adds
            # CUDA_HOME/include and CUDA_HOME/lib, which are insufficient here.
            # These are compile/link search paths, never runtime LD overrides.
            'CPLUS_INCLUDE_PATH': str(TOOLKIT / 'targets/x86_64-linux/include'),
            'C_INCLUDE_PATH': str(TOOLKIT / 'targets/x86_64-linux/include'),
            'LIBRARY_PATH': str(TOOLKIT / 'targets/x86_64-linux/lib'),
            'TORCH_CUDA_ARCH_LIST': '12.0', 'MAX_JOBS': '2', 'NVCC_THREADS': '1',
            'FLASH_ATTENTION_FORCE_BUILD': 'TRUE', 'FLASH_ATTN_CUDA_ARCHS': '120',
        })
    return env


def bwrap_command(args, temporary, command=None):
    argv = ['/usr/bin/bwrap', '--die-with-parent', '--new-session', '--unshare-user',
            '--unshare-pid', '--unshare-ipc', '--unshare-uts', '--cap-drop', 'ALL', '--clearenv']
    if args.profile != 'download':
        argv += ['--unshare-net']
    argv += ['--ro-bind', '/', '/', '--bind', str(ROOT), str(ROOT),
             '--ro-bind', str(TOOLKIT), str(TOOLKIT)]
    if args.profile != 'install':
        argv += ['--ro-bind', str(PYENV), str(PYENV)]
    argv += ['--bind', str(temporary), '/tmp', '--bind', str(temporary), '/var/tmp',
             '--proc', '/proc', '--ro-bind', '/proc/sys', '/proc/sys',
             '--dev', '/dev', '--bind', str(temporary / 'shm'), '/dev/shm',
             '--chdir', str(args.cwd)]
    if args.profile == 'gpu':
        for node in gpu_nodes(args.device_minor):
            argv += ['--dev-bind', node, node]
    for key, value in environment(args.profile, args.gpu_uuid, temporary).items():
        argv += ['--setenv', key, value]
    return argv + ['--'] + list(command if command is not None else args.command)


def plan(args):
    validate(args)
    return {'mode': 'plan', 'executed': False, 'profile': args.profile, 'label': args.label,
            'command': args.command, 'cwd': str(args.cwd), 'timeout_seconds': args.timeout_seconds,
            'network_allowed': args.profile == 'download', 'python_environment_writable': args.profile == 'install',
            'gpu_uuid': args.gpu_uuid, 'gpu_index': args.gpu_index, 'device_minor': args.device_minor,
            'gpu_query_fields': GPU_FIELDS.split(',') if args.profile == 'gpu' else [],
            'gpu_preflight': 'fixed selected-UUID driver/compute queries in controller PID namespace, plus isolated queries' if args.profile == 'gpu' else None,
            'sampler_interval': 'query duration plus nominal 1 second; command JSON holds timestamps',
            'bwrap_argv': bwrap_command(args, ROOT / 'tmp/official-example-<RUN_ID>'),
            'limits': ['GPU control/UVM are shared; no exclusive reservation or hard GPU memory cap.',
                       'Public download only; never pass credentials into this logging runner.',
                       'No fallback, automatic retry, environment activation, or system changes.']}


def verify_mapping(gpu_uuid, minor):
    matches = []
    for path in sorted(Path('/proc/driver/nvidia/gpus').glob('*/information')):
        fields = {}
        for line in path.read_text().splitlines():
            key, separator, value = line.partition(':')
            if separator:
                fields[key.strip()] = value.strip()
        if fields.get('GPU UUID', '').lower() == gpu_uuid.lower():
            matches.append((path, fields))
    require(len(matches) == 1, 'UUID has no unique driver-proc mapping.')
    path, fields = matches[0]
    require(fields.get('Device Minor', '').isdigit() and int(fields['Device Minor']) == minor,
            'GPU UUID/device minor mismatch.')
    for node in gpu_nodes(minor):
        data = Path(node).lstat()
        require(stat.S_ISCHR(data.st_mode), 'Required GPU node missing, symlinked, or not a character device.')
        if node == f'/dev/nvidia{minor}':
            require(os.minor(data.st_rdev) == minor, 'GPU character device minor mismatch.')
    return {'gpu_uuid': gpu_uuid, 'device_minor': minor, 'driver_metadata_path': str(path),
            'bus_location': fields.get('Bus Location'), 'nodes': gpu_nodes(minor)}


def pci_identity(value):
    match = re.fullmatch(r'([0-9a-fA-F]{1,8}):([0-9a-fA-F]{2}):([0-9a-fA-F]{2})\.([0-7])', value)
    require(match is not None, 'Unrecognized GPU PCI bus identifier.')
    return tuple(int(part, 16) for part in match.groups())


def validate_gpu_row(text, args, *, host_preflight=False, expected_pci_bus_id=None):
    rows = list(csv.reader(line for line in text.splitlines() if line.strip()))
    require(len(rows) == 1 and len(rows[0]) == len(GPU_FIELDS.split(',')), 'Unexpected selected-GPU query format.')
    row = [value.strip() for value in rows[0]]
    # NVML enumerates the sole device as index 0 inside the filtered namespace.
    # Preserve the user-selected host index check and bridge scopes by UUID/PCI.
    expected_index = args.gpu_index if host_preflight else 0
    require(row[0].isdigit() and int(row[0]) == expected_index and row[1].lower() == args.gpu_uuid.lower(),
            'Selected GPU index/UUID changed or is ambiguous.')
    require(host_preflight or expected_pci_bus_id is not None, 'Isolated GPU query needs a previously checked host PCI identity.')
    if expected_pci_bus_id is not None:
        require(pci_identity(row[2]) == pci_identity(expected_pci_bus_id), 'Selected GPU PCI identity changed between scopes.')
    return dict(zip(GPU_FIELDS.split(','), row))


def gpu_query_command(args, compute=False):
    """Fixed read-only selected-device query; no arbitrary NVIDIA options."""
    fields = 'pid,gpu_uuid,used_gpu_memory' if compute else GPU_FIELDS
    option = '--query-compute-apps=' if compute else '--query-gpu='
    return ['/usr/bin/nvidia-smi', '--id=' + args.gpu_uuid, option + fields,
            '--format=csv,noheader,nounits']


def write_json(path, value):
    checked_path(path)
    require(not path.is_symlink(), 'Refusing symlink log file.')
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


class Recorder:
    def __init__(self, directory):
        self.directory = directory

    def command(self, label, argv, timeout, monitor=None, read_output=False, child_env=None):
        """Execute-only. Each call has its own argv/stdout/stderr/result files."""
        import subprocess
        target = self.directory / label
        target.mkdir(mode=0o700, exist_ok=False)
        record = {'argv': argv, 'cwd': str(ROOT), 'started_at': now(), 'timeout_seconds': timeout,
                  'process_started': False, 'exit_code': None, 'automatic_retry': False}
        write_json(target / 'command.json', record)
        process = None
        failure = None
        try:
            with (target / 'stdout.log').open('w') as out, (target / 'stderr.log').open('w') as err:
                process = subprocess.Popen(argv, cwd=ROOT, env=MINIMAL_ENV if child_env is None else child_env, stdin=subprocess.DEVNULL,
                                           stdout=out, stderr=err, start_new_session=True)
                record.update(process_started=True, process_started_at=now())
                deadline = time.monotonic() + timeout
                sample = 0
                while process.poll() is None:
                    require(time.monotonic() < deadline, 'Command time budget exceeded.')
                    if monitor is not None:
                        monitor(sample)
                        sample += 1
                    if process.poll() is None:
                        time.sleep(min(1.0 if monitor else 0.2, max(0, deadline - time.monotonic())))
                record.update(exit_code=process.returncode, sampler_count=sample)
        except BaseException as error:
            failure = error
            record.update(error_type=type(error).__name__,
                          reason=str(error) if isinstance(error, Stopped) else 'Command launch/wait failed.')
            if process is None:
                record['launch_error'] = type(error).__name__
            elif process.poll() is None:
                record['termination_requested'] = True
                try:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                    record.update(interrupted=True, terminated=True)
                except BaseException as stop_error:
                    record['termination_error_type'] = type(stop_error).__name__
            if process is not None:
                record['exit_code'] = process.poll()
        finally:
            record['ended_at'] = now()
            write_json(target / 'result.json', record)
        if failure is not None:
            raise failure
        # Build/example logs can be large; only small metadata queries need text.
        return record, (target / 'stdout.log').read_text(errors='replace') if read_output else None


def execute(args):
    import resource
    validate(args)
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, 'Controller requires -I -B -S.')
    require(ROOT.resolve() == ROOT, 'Workspace root must be canonical.')
    for path in (PYENV, TOOLKIT, args.cwd):
        require(checked_path(path).is_dir(), 'Required workspace directory is missing.')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.umask(0o077)
    run_id = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + args.label + '-' + uuid.uuid4().hex[:10]
    run = checked_path(BASE / 'runs' / run_id)
    temporary = checked_path(ROOT / 'tmp' / ('official-example-' + run_id))
    run.mkdir(parents=True, mode=0o700, exist_ok=False)
    temporary.mkdir(parents=True, mode=0o700, exist_ok=False)
    recorder = Recorder(run)
    state = {'run_id': run_id, 'profile': args.profile, 'label': args.label, 'started_at': now(),
             'phase': 'preflight', 'command_exit_code': None, 'command_passed': False,
             'gpu_uuid': args.gpu_uuid, 'gpu_index': args.gpu_index, 'device_minor': args.device_minor,
             'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    gpu_ready = False
    primary_error = None
    host_identity = {}
    mapping = None

    def query(label, compute=False, host_preflight=False):
        argv = gpu_query_command(args, compute)
        # Internal PID namespaces alone cannot establish that host jobs are absent.
        # Only these fixed read-only preflight queries run in the controller PID
        # namespace; the user's workload retains its separate PID namespace.
        query_env = dict(MINIMAL_ENV, TMPDIR=str(temporary), TMP=str(temporary), TEMP=str(temporary))
        if not host_preflight:
            argv = bwrap_command(args, temporary, argv)
        result, output = recorder.command(label, argv, QUERY_TIMEOUT, read_output=True, child_env=query_env)
        require(result['exit_code'] == 0, label + ' failed; no retry or isolation fallback.')
        if not compute:
            expected_pci = mapping.get('bus_location') if host_preflight else host_identity.get('pci.bus_id')
            row = validate_gpu_row(output, args, host_preflight=host_preflight, expected_pci_bus_id=expected_pci)
            if host_preflight:
                host_identity.update(row)
        return output

    try:
        write_json(run / 'status.json', state)
        write_json(run / 'plan.json', plan(args))
        env = environment(args.profile, args.gpu_uuid, temporary)
        file_keys = {'CONDARC', 'CUDACXX'}
        for key, value in env.items():
            if key not in file_keys and value.startswith(str(ROOT) + '/') and ':' not in value:
                checked_path(value).mkdir(parents=True, mode=0o700, exist_ok=True)
        (temporary / 'shm').mkdir(mode=0o700)
        require(not any((ROOT / 'cache/git-template-empty').iterdir()), 'Git template directory must be empty.')
        if args.profile == 'gpu':
            # Verify UUID/minor before even compiler preflight gets GPU nodes.
            mapping = verify_mapping(args.gpu_uuid, args.device_minor)
            write_json(run / 'device-mapping.json', mapping)
        if args.profile in ('build', 'gpu'):
            for label, argv, expected in [
                ('nvcc-version', [str(TOOLKIT / 'bin/nvcc'), '--version'], 'V12.8.93'),
                ('gcc-version', ['/usr/bin/gcc-13', '-dumpfullversion'], '13.3.0'),
                ('gxx-version', ['/usr/bin/g++-13', '-dumpfullversion'], '13.3.0'),
            ]:
                result, output = recorder.command(label, bwrap_command(args, temporary, argv), QUERY_TIMEOUT, read_output=True)
                matched = expected in output if label == 'nvcc-version' else output.strip() == expected
                require(result['exit_code'] == 0 and matched, 'Pinned compiler verification failed.')
        if args.profile == 'gpu':
            state['controller_pid_namespace'] = os.readlink('/proc/self/ns/pid')
            query('host-selected-gpu', host_preflight=True)
            query('gpu-driver-info')
            applications = query('gpu-existing-compute-apps', compute=True)
            require(not applications.strip(), 'Selected GPU has reported compute processes; command not started.')
            host_applications = query('host-existing-compute-apps', compute=True, host_preflight=True)
            require(not host_applications.strip(), 'Controller-namespace query reports selected-GPU compute processes; command not started.')
            state['host_compute_preflight_passed'] = True
            query('gpu-usage-before')
            gpu_ready = True
        state['phase'] = 'command'
        write_json(run / 'status.json', state)
        monitor = (lambda index: query(f'gpu-usage-{index:06d}')) if args.profile == 'gpu' else None
        result, _ = recorder.command('command', bwrap_command(args, temporary), args.timeout_seconds, monitor)
        state.update(command_exit_code=result['exit_code'], command_passed=result['exit_code'] == 0)
        require(result['exit_code'] == 0, 'Command returned nonzero; inspect command logs.')
    except BaseException as error:
        primary_error = error
        state.update(failed_stage=state['phase'], error_type=type(error).__name__,
                     reason=str(error) if isinstance(error, Stopped) else 'Preparation or execution failed.')
        result_path = run / 'command/result.json'
        if result_path.exists():
            result = json.loads(result_path.read_text())
            state.update(command_exit_code=result['exit_code'], command_passed=result['exit_code'] == 0)
    finally:
        if gpu_ready:
            try:
                query('gpu-usage-after')
                state['gpu_final_query_passed'] = True
            except BaseException as error:
                state.update(gpu_final_query_passed=False, final_query_error_type=type(error).__name__)
                if primary_error is None:
                    primary_error = error
                    state.update(failed_stage='gpu-usage-after', reason='Final GPU usage query failed.')
        state.update(phase='completed' if primary_error is None else 'stopped', ended_at=now(),
                     exit_code=0 if primary_error is None else 1, automatic_retry=False, protections_weakened=False)
        write_json(run / 'status.json', state)
        print(json.dumps({'phase': state['phase'], 'exit_code': state['exit_code'], 'logs': str(run),
                          'command_exit_code': state['command_exit_code']}, ensure_ascii=False), flush=True)
    return state['exit_code']


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--plan', action='store_true', help='Default: print a plan without subprocesses or writes.')
    mode.add_argument('--execute', action='store_true', help='Execute the reviewed command under the selected profile.')
    parser.add_argument('--profile', choices=PROFILES, required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--cwd', type=Path, default=ROOT)
    parser.add_argument('--gpu-uuid')
    parser.add_argument('--gpu-index', type=int)
    parser.add_argument('--device-minor', type=int)
    parser.add_argument('--timeout-seconds', type=int, default=3600)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command[:1] == ['--']:
        args.command = args.command[1:]
    return args


def main(argv=None):
    try:
        args = parse_args(argv)
        if args.execute:
            return execute(args)
        print(json.dumps(plan(args), ensure_ascii=False, indent=2))
        return 0
    except Stopped as error:
        print(json.dumps({'phase': 'stopped', 'reason': str(error), 'exit_code': 1}), file=sys.stderr)
        return 1
    except Exception as error:
        print(json.dumps({'phase': 'stopped', 'error_type': type(error).__name__, 'exit_code': 1}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
