"""User-terminal continuation: wait for existing work, then one official example.

No automatic Git upload, download, rebuild, version replacement, or failed-stage
retry. Default is a read-only plan. --execute is intended for the user's host
terminal, not for Codex to launch. Ctrl+C never kills an already-started worker;
the next invocation detects that worker and waits instead of duplicating it.
"""
import argparse
import csv
import datetime
import fcntl
import hashlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
BASE = ROOT / 'logs/official-example-20260921'
RUNNER = BASE / 'workspace_runner.py'
PYTHON = ROOT / 'envs/physxgen/bin/python'
SITE = ROOT / 'envs/physxgen/lib/python3.10/site-packages'
WORK = ROOT / 'sources/physx-example-work-4f54e750a309'
SYSTEM_PYTHON = '/usr/bin/python3'
CLEAN_ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}
DEPENDENCIES = [
    BASE / 'runs/20260921T090259Z-flash-attention-wheel-conda-paths-2d7b8ff070/status.json',
    BASE / 'runs/20260921T090509Z-prepare-models-9fb53e503a/status.json',
]
GPUS = [
    {'uuid': 'GPU-843dced4-ee97-dbb8-36c9-343fe13b7647', 'index': 1, 'minor': 1},
    {'uuid': 'GPU-ff124b39-8b48-7d2a-bf74-bf6a5c8f1716', 'index': 0, 'minor': 0},
]
TERMINAL_LABELS = ('terminal-flash-inspect', 'terminal-flash-install', 'terminal-flash-smoke', 'official-table', 'terminal-output-verify')


class Stopped(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise Stopped(message)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def atomic_json(path, data):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.partial')
    with temporary.open('x') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    os.replace(temporary, path)


def read_json(path):
    # Historical workers update status in place. Tolerate only transient partial reads.
    for attempt in range(20):
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            if attempt == 19:
                raise Stopped('상태 파일을 읽을 수 없습니다. 재실행하지 않고 기록 검토가 필요합니다: ' + str(path))
            time.sleep(0.1)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def acquire_lock(path):
    require(not path.is_symlink(), '잠금 파일이 symlink입니다.')
    stream = path.open('a+')
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        stream.close()
        raise Stopped('같은 이어가기 스크립트가 실행 중입니다. 중복 실행하지 않았습니다.')
    # Never unlink: all invocations must lock the same inode.
    return stream


def process_identity(pid):
    try:
        directory = Path('/proc') / str(pid)
        raw = (directory / 'stat').read_text()
        fields = raw[raw.rfind(')') + 2:].split()
        if fields[0] == 'Z':
            return None
        return {'pid': int(pid), 'start_ticks': int(fields[19]),
                'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None


def controllers(label):
    matches = []
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit():
            continue
        try:
            arguments = (directory / 'cmdline').read_bytes().split(b'\0')
            arguments = [x.decode() for x in arguments if x]
            if str(RUNNER) not in arguments or '--label' not in arguments:
                continue
            if arguments[arguments.index('--label') + 1] != label:
                continue
            # The controller argv includes the runner as the Python script,
            # whereas the inner bwrap workload does not.
            require(arguments[0] == SYSTEM_PYTHON, '예상하지 못한 실행기 프로세스입니다.')
            identity = process_identity(directory.name)
            if identity:
                matches.append(identity)
        except (FileNotFoundError, ProcessLookupError, PermissionError, UnicodeDecodeError, IndexError):
            continue
    return matches


def run_decision(status, live):
    if status['phase'] == 'completed':
        require(status.get('exit_code') == 0 and status.get('command_exit_code') == 0,
                '완료 상태와 종료 코드가 일치하지 않습니다.')
        return 'completed'
    if status['phase'] == 'stopped':
        raise Stopped('기존 실행이 실패했습니다. 자동 재시도 없이 Codex 로그 검토가 필요합니다: ' + status['label'])
    require(status['phase'] in ('preflight', 'command'), '알 수 없는 실행 상태입니다.')
    require(len(live) == 1, '진행 중 상태와 실제 프로세스가 일치하지 않습니다. 중복 실행하지 않고 중단합니다.')
    return 'wait'


class Session:
    def __init__(self):
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:10]
        self.directory = BASE / 'terminal-runs' / stamp
        self.directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.output = (self.directory / 'stdout.log').open('a', buffering=1)
        self.error = (self.directory / 'stderr.log').open('a', buffering=1)
        self.state = {'started_at': now(), 'status': 'running', 'exit_code': None,
                      'argv': [SYSTEM_PYTHON, '-u', '-I', '-B', '-S', str(Path(__file__)), '--execute'],
                      'pid_identity': process_identity(os.getpid()), 'git_upload': False,
                      'stages': [], 'script_sha256': digest(Path(__file__))}
        atomic_json(self.directory / 'command.json', self.state)
        self.save()

    def save(self):
        atomic_json(self.directory / 'result.json', self.state)

    def say(self, message):
        text = '[' + now() + '] ' + message
        print(text, flush=True)
        print(text, file=self.output, flush=True)

    def versions(self, name):
        versions = {d.metadata['Name'].lower().replace('_', '-'): d.version for d in md.distributions(path=[str(SITE)])}
        require(versions.get('torch') == '2.7.1+cu128' and versions.get('torchvision') == '0.22.1+cu128',
                '고정 PyTorch/torchvision 버전이 바뀌었습니다.')
        baseline = read_json(BASE / 'terminal-environment-baseline.json')
        expected = dict(baseline['distributions'])
        if 'flash-attn' in versions:
            expected['flash-attn'] = '2.8.3'
        require(versions == expected, '준비 시점의 고정 패키지 목록과 실제 환경이 다릅니다. 설치를 시작하지 않습니다.')
        atomic_json(self.directory / name, {'recorded_at': now(), 'distributions': versions,
                    'expected_python': '3.10.21', 'expected_nvcc': '12.8.93', 'expected_gcc': '13.3.0',
                    'versions_observation': 'Package metadata read without importing packages. Actual interpreter/compiler versions are separately logged by child stages.'})
        return versions

    def wait_run(self, path):
        previously_live = None
        while True:
            status = read_json(path)
            live = controllers(status['label']) if status['phase'] not in ('completed', 'stopped') else []
            if status['phase'] not in ('completed', 'stopped') and not live:
                # A worker can publish its final status between the two reads.
                status = read_json(path)
            decision = run_decision(status, live)
            if decision == 'completed':
                self.say('기존 단계 완료 확인: ' + status['label'])
                return status
            if previously_live is not None:
                require(live[0] == previously_live, '실행 중 프로세스의 PID/시작 시각이 바뀌었습니다.')
            previously_live = live[0]
            self.state['waiting_for'] = {'status': str(path), 'process': live[0]}
            self.save()
            self.say('실행 중인 작업을 그대로 기다립니다: ' + status['label'] + ' (PID ' + str(live[0]['pid']) + ')')
            time.sleep(15)

    def previous(self, label):
        paths = [p for p in (BASE / 'runs').glob('*/status.json') if read_json(p).get('label') == label]
        require(len(paths) <= 1, '같은 단계 기록이 여러 개입니다. 임의 선택하지 않고 검토를 요청합니다: ' + label)
        if not paths:
            launches = list((BASE / 'terminal-runs').glob('*/stage-' + label + '/command.json'))
            require(len(launches) <= 1, '이전 터미널 실행 시도가 여러 개입니다. 자동 재시도하지 않습니다: ' + label)
            if launches:
                launch = read_json(launches[0])
                identity = launch.get('process')
                require(identity is not None and process_identity(identity['pid']) == identity,
                        '이전 실행을 시작한 기록은 있지만 완료 상태/살아 있는 프로세스를 확인할 수 없습니다. 재실행 없이 Codex 검토가 필요합니다: ' + label)
                self.say('상태 파일 생성 전 시작된 작업을 기다립니다: ' + label)
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    time.sleep(1)
                    paths = [p for p in (BASE / 'runs').glob('*/status.json') if read_json(p).get('label') == label]
                    if paths:
                        require(len(paths) == 1, '같은 단계의 중복 실행 기록입니다.')
                        self.wait_run(paths[0])
                        return paths[0].parent
                    require(process_identity(identity['pid']) == identity,
                            '실행기가 최종 상태 없이 종료됐습니다. 자동 재시도하지 않습니다: ' + label)
                raise Stopped('진행 중 프로세스의 상태 파일을 확인할 수 없습니다. 작업을 종료하지 않았습니다: ' + label)
            require(not controllers(label), '시작 중인 같은 작업을 발견했습니다. 잠시 후 상태를 확인하세요.')
            return None
        self.wait_run(paths[0])
        return paths[0].parent

    def run(self, label, argv):
        directory = self.directory / ('stage-' + label)
        directory.mkdir(mode=0o700, exist_ok=False)
        self.versions(label + '-versions-before.json')
        record = {'argv': argv, 'cwd': str(ROOT), 'started_at': now(), 'exit_code': None}
        atomic_json(directory / 'command.json', record)
        self.state['stages'].append({'label': label, 'directory': str(directory), 'state': 'running'})
        self.save()
        self.say('시작: ' + label + ' / 로그: ' + str(directory))
        process = None
        try:
            with (directory / 'stdout.log').open('wb') as out, (directory / 'stderr.log').open('wb') as err:
                process = subprocess.Popen(argv, cwd=ROOT, env=CLEAN_ENV, stdin=subprocess.DEVNULL,
                                           stdout=out, stderr=err, start_new_session=True)
                record['process'] = process_identity(process.pid)
                atomic_json(directory / 'command.json', record)
                announced = False
                while process.poll() is None:
                    # The worker records workload stdout/stderr continuously, independently of this terminal.
                    candidates = [p for p in (BASE / 'runs').glob('*/status.json') if read_json(p).get('label') == label]
                    if candidates and not announced:
                        self.say('실시간 상세 로그: ' + str(candidates[0].parent / 'command'))
                        announced = True
                    time.sleep(1)
                record['exit_code'] = process.returncode
        except KeyboardInterrupt:
            record['detached_on_interrupt'] = True
            record['reason'] = 'Terminal controller interrupted; worker deliberately left running. Next invocation detects and waits for it.'
            raise
        finally:
            record['finished_at'] = now()
            atomic_json(directory / 'result.json', record)
            self.state['stages'][-1].update(state='passed' if record['exit_code'] == 0 else 'stopped', exit_code=record['exit_code'])
            self.save()
        require(record['exit_code'] == 0, '단계 실패. 이후 단계는 시작하지 않습니다: ' + label + ' / ' + str(directory))
        self.say('종료 0: ' + label)
        self.versions(label + '-versions-after.json')
        return self.previous(label)


def runner_arguments(profile, label, command, gpu=None, cwd=ROOT, timeout=3600):
    argv = [SYSTEM_PYTHON, '-I', '-B', '-S', str(RUNNER), '--execute', '--profile', profile,
            '--label', label, '--cwd', str(cwd), '--timeout-seconds', str(timeout)]
    if gpu:
        argv += ['--gpu-uuid', gpu['uuid'], '--gpu-index', str(gpu['index']), '--device-minor', str(gpu['minor'])]
    return argv + ['--'] + command


def target(script, *args):
    return [str(PYTHON), '-I', '-B', '-S', str(BASE / script), *map(str, args)]


def choose_gpu(session, candidates=None):
    candidates = GPUS if candidates is None else candidates
    for gpu in candidates:
        directory = session.directory / ('gpu-selection-' + str(gpu['index']))
        directory.mkdir()
        argv = ['/usr/bin/nvidia-smi', '--id=' + gpu['uuid'], '--query-compute-apps=pid,gpu_uuid,used_gpu_memory', '--format=csv,noheader,nounits']
        record = {'argv': argv, 'started_at': now()}
        with (directory / 'stdout.log').open('w') as out, (directory / 'stderr.log').open('w') as err:
            result = subprocess.run(argv, env=CLEAN_ENV, stdin=subprocess.DEVNULL, stdout=out, stderr=err, timeout=15)
        record.update(exit_code=result.returncode, finished_at=now())
        atomic_json(directory / 'command-result.json', record)
        require(result.returncode == 0, 'GPU 상태 조회 실패. 보호 설정을 바꾸지 않고 중단합니다.')
        if not (directory / 'stdout.log').read_text().strip():
            session.say('계산 프로세스가 없는 GPU 후보: 호스트 ' + str(gpu['index']) + ' / ' + gpu['uuid'])
            return gpu
    raise Stopped('선택 가능한 GPU가 계산 작업 중입니다. 다른 작업을 중단하지 않았습니다. 비워진 뒤 같은 명령을 실행하세요.')


def wait_wheel_receipt(session):
    receipt = BASE / 'flash-attention-build/result.json'
    inspected = session.previous('terminal-flash-inspect')
    if inspected:
        command = read_json(inspected / 'plan.json')['command']
        require(command[:5] == target('inspect_flash_wheel.py') and '--output-dir' in command,
                '기존 정적 검사 명령이 일치하지 않습니다.')
        receipt = Path(command[command.index('--output-dir') + 1]) / 'result.json'
    elif not receipt.exists():
        destination = session.directory / 'flash-wheel-inspection'
        session.run('terminal-flash-inspect', runner_arguments('build', 'terminal-flash-inspect',
                    target('inspect_flash_wheel.py', '--output-dir', destination), timeout=600))
        receipt = destination / 'result.json'
    require(receipt.resolve().is_relative_to(BASE), '정적 검사 기록 경로 오류')
    result = read_json(receipt)
    require(result.get('version') == '2.8.3' and result.get('source_commit') == '060c9188beec3a8b62b33a3bfa6d5d2d44975fab', 'wheel 소스/버전 기록 불일치')
    require(result.get('fetched_source_preserved') and result.get('original_build_source_unmodified'), '공식 소스 변경 검토 필요')
    wheel = Path(result['wheel'])
    require(wheel.resolve().is_relative_to(ROOT / 'cache/wheels/flash-attention') and wheel.is_file(), 'wheel 경로 오류')
    require(wheel.stat().st_size == result['wheel_size'] and digest(wheel) == result['wheel_sha256'], 'wheel 크기/해시 불일치')
    atomic_json(session.directory / 'flash-wheel-verified.json', result)
    return wheel


def checked_gpu_from_run(run):
    status = read_json(run / 'status.json')
    plan = read_json(run / 'plan.json')
    matches = [gpu for gpu in GPUS if gpu['uuid'] == status.get('gpu_uuid')]
    require(len(matches) == 1, '이전 검사 GPU UUID를 복원할 수 없습니다.')
    gpu = matches[0]
    require(status.get('gpu_index') == gpu['index'] and status.get('device_minor') == gpu['minor'] and
            plan.get('gpu_uuid') == gpu['uuid'] and plan.get('gpu_index') == gpu['index'] and
            plan.get('device_minor') == gpu['minor'], '이전 검사 GPU 번호/UUID가 일치하지 않습니다.')
    return gpu


def verify_validation_binding(validation, example, output):
    command = read_json(validation / 'plan.json')['command']
    expected_prefix = target('validate_example_outputs.py', '--execute', '--output-dir', output,
                             '--execution-status', example / 'status.json', '--report')
    require(command[:-1] == expected_prefix, '이전 출력 검사 명령이 이 예제와 연결되지 않습니다.')
    report_path = Path(command[-1])
    require(report_path.resolve().is_relative_to(BASE), '출력 검증 보고서 경로 오류')
    report = read_json(report_path)
    require(report.get('status') == 'passed' and report.get('exit_code') == 0 and
            report.get('output_directory') == str(output), '출력 검사 보고서가 성공/출력 경로와 일치하지 않습니다.')
    provenance = report.get('checks', {}).get('provenance', {})
    require(provenance.get('status') == 'passed', '출력 provenance 검증이 성공하지 않았습니다.')
    evidence = provenance['result']['execution_status']
    require(evidence['path'] == str((example / 'status.json').relative_to(ROOT)) and
            evidence['sha256'] == digest(example / 'status.json'), '출력 보고서가 다른 실행 기록을 가리킵니다.')
    artifacts = report.get('all_output_files', [])
    require(bool(artifacts), '검증 보고서에 출력 파일 목록이 없습니다.')
    for artifact in artifacts:
        path = ROOT / artifact['path']
        require(path.resolve().is_relative_to(output) and path.is_file() and
                path.stat().st_size == artifact['size_bytes'], '검증된 출력 파일이 없어졌거나 크기가 바뀌었습니다: ' + str(path))
    return report_path


def execution_record(run):
    messages = []
    for line in (run / 'command/stdout.log').read_text(errors='replace').splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict) and 'execution_record' in value:
                messages.append(value)
        except json.JSONDecodeError:
            pass
    require(len(messages) == 1 and messages[0].get('exit_code') == 0, '성공한 예제의 출력 경로를 확정할 수 없습니다.')
    path = Path(messages[0]['execution_record'])
    require(path.resolve().is_relative_to(ROOT / 'outputs/official-example'), '예제 출력 경로 오류')
    record = read_json(path)
    require(record.get('exit_code') == 0 and record.get('status') == 'example_returned', '예제 내부 완료 기록 불일치')
    return path, record


def continue_work(session):
    # Do not start anything while an earlier authorized worker is still running.
    for path in DEPENDENCIES:
        session.wait_run(path)
    for path in sorted((BASE / 'runs').glob('*/status.json')):
        state = read_json(path)
        if state['phase'] not in ('completed', 'stopped'):
            session.wait_run(path)
    wheel = wait_wheel_receipt(session)
    versions = session.versions('environment-before.json')
    previous_install = session.previous('terminal-flash-install')
    if previous_install:
        require(versions.get('flash-attn') == '2.8.3', '완료 기록과 실제 FlashAttention 설치 상태 불일치')
        session.say('완료된 FlashAttention 설치를 건너뜁니다.')
    else:
        require('flash-attn' not in versions, '별도 설치된 FlashAttention이 있습니다. 중복 설치 없이 검토가 필요합니다.')
        session.run('terminal-flash-install', runner_arguments('install', 'terminal-flash-install', target('install_verified_wheels.py', wheel)))
    gpu = None
    smoke = session.previous('terminal-flash-smoke')
    if not smoke:
        gpu = choose_gpu(session)
        smoke = session.run('terminal-flash-smoke', runner_arguments('gpu', 'terminal-flash-smoke',
                    target('check_extensions.py', '--case', 'flashattn', '--execute', '--gpu-uuid', gpu['uuid']), gpu, timeout=300))
    else:
        session.say('완료된 FlashAttention 실제 연산 검사를 건너뜁니다.')
        gpu = checked_gpu_from_run(smoke)
    example = session.previous('official-table')
    if not example:
        # Any other official example evidence, including failed or interrupted
        # attempts, requires review. Never create a second inference blindly.
        evidence = list((ROOT / 'outputs/official-example').glob('*/execution.json'))
        other_runs = list((BASE / 'runs').glob('*official-table*/status.json'))
        require(not evidence and not other_runs, '기존 예제 기록이 있습니다. 중복 추론 없이 Codex 검토가 필요합니다.')
        if not any(stage['label'] == 'terminal-flash-smoke' for stage in session.state['stages']):
            gpu = choose_gpu(session, candidates=[gpu])
        example = session.run('official-table', runner_arguments('gpu', 'official-table',
                    target('run_example.py', '--gpu-uuid', gpu['uuid']), gpu, WORK, 7200))
    else:
        session.say('성공한 공식 예제를 다시 실행하지 않습니다. 출력 검사만 이어갑니다.')
    record_path, record = execution_record(example)
    output = Path(record['output_files_directory'])
    validation = session.previous('terminal-output-verify')
    if not validation:
        validation_report = session.directory / 'output-validation.json'
        validation = session.run('terminal-output-verify', runner_arguments('build', 'terminal-output-verify',
                    target('validate_example_outputs.py', '--execute', '--output-dir', output,
                           '--execution-status', example / 'status.json', '--report', validation_report), timeout=1800))
    validated_report = verify_validation_binding(validation, example, output)
    session.state.update(status='completed', exit_code=0, official_example_run=str(example),
                         example_execution_record=str(record_path), output_directory=str(output),
                         validation_run=str(validation), validation_report=str(validated_report),
                         next_action='Codex reviews logs and artifacts, then commits/pushes only reviewed 04_PhysX-3D records.')
    session.say('예제 실행과 자동 출력 검사가 끝났습니다. Git 업로드는 하지 않았습니다.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'executed': False, 'steps': ['wait existing build/download', 'verify exact wheel',
              'install missing FlashAttention only', 'check attention on one free GPU', 'run one table example',
              'validate existing outputs on CPU'], 'automatic_git_upload': False,
              'automatic_download_or_rebuild': False, 'log_root': str(BASE / 'terminal-runs')}, ensure_ascii=False, indent=2))
        return 0
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, '명령에 -I -B -S를 사용하세요.')
    require(ROOT.resolve() == ROOT and BASE.resolve() == BASE, '작업 루트 경로 오류')
    os.umask(0o077)
    session = Session()
    lock = None
    try:
        lock = acquire_lock(BASE / 'terminal-handoff.lock')
        session.say('로그 폴더: ' + str(session.directory))
        session.say('기존 작업을 중단하지 않으며 실패한 실제 단계는 자동 반복하지 않습니다.')
        prepared = read_json(BASE / 'terminal-preparation-manifest.json')
        for item in prepared['scripts']:
            path = Path(item['path'])
            require(path.resolve().is_relative_to(BASE) and digest(path) == item['sha256'],
                    '준비 후 실행 코드가 바뀌었습니다: ' + str(path))
        atomic_json(session.directory / 'preparation-manifest.json', prepared)
        continue_work(session)
    except KeyboardInterrupt:
        session.state.update(status='interrupted', exit_code=130,
                             reason='Terminal interrupted; already-started workers are left running. Re-entry waits for them and checks results.')
        session.say('터미널 제어만 중단했습니다. 이미 시작한 작업은 중단하지 않았습니다. 같은 명령은 진행 중 작업을 먼저 확인합니다.')
    except BaseException as error:
        message = str(error) if isinstance(error, Stopped) else type(error).__name__ + ': ' + str(error)
        session.state.update(status='stopped', exit_code=1, reason=message)
        print(message, file=session.error, flush=True)
        session.say('중단: ' + message)
    finally:
        session.state['finished_at'] = now()
        session.save()
        if lock:
            lock.close()
        session.say('결과 파일: ' + str(session.directory / 'result.json'))
    return session.state['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
