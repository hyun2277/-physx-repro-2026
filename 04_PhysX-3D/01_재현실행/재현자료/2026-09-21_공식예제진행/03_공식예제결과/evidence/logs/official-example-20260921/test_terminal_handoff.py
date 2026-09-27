"""Stdlib-only tests: temporary workspace records and mocked processes only.

No installer, builder, CUDA program, model, real subprocess, or live lock is used.
Run with /usr/bin/python3 -I -B -S this_file.py. Test files stay in ROOT/tmp.
"""
import contextlib
import datetime
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest import mock
import uuid
import zipfile

REAL_ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
SOURCE = REAL_ROOT / 'logs/official-example-20260921/terminal_handoff.py'
SPEC = importlib.util.spec_from_file_location('handoff_under_test', SOURCE)
H = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(H)

IDENTITY = {'pid': 12345, 'start_ticks': 2222, 'boot_id': 'test-boot'}


def status(phase='completed', label='stage', code=0, command_code=0):
    return {'phase': phase, 'label': label, 'exit_code': code, 'command_exit_code': command_code}


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        temporary = self.stack.enter_context(tempfile.TemporaryDirectory(prefix='handoff-mock-tests-', dir=REAL_ROOT / 'tmp'))
        self.root = Path(temporary)
        self.base = self.root / 'logs'
        (self.base / 'runs').mkdir(parents=True)
        self.stack.enter_context(mock.patch.object(H, 'ROOT', self.root))
        self.stack.enter_context(mock.patch.object(H, 'BASE', self.base))
        self.stack.enter_context(mock.patch.object(H, 'DEPENDENCIES', []))
        self.stack.enter_context(mock.patch.object(H, 'process_identity', return_value=dict(IDENTITY)))
        self.stack.enter_context(mock.patch.object(H, 'controllers', return_value=[]))
        self.stack.enter_context(mock.patch.object(H.time, 'sleep'))
        self.forbid_popen = self.stack.enter_context(mock.patch.object(H.subprocess, 'Popen', side_effect=AssertionError('Real Popen prohibited')))
        self.forbid_run = self.stack.enter_context(mock.patch.object(H.subprocess, 'run', side_effect=AssertionError('Real subprocess.run prohibited')))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def session(self):
        result = H.Session()
        self.addCleanup(result.output.close)
        self.addCleanup(result.error.close)
        return result

    def worker_record(self, name='run-one', value=None):
        path = self.base / 'runs' / name / 'status.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(value or status()))
        return path

    def test_completed_requires_both_success_codes(self):
        self.assertEqual(H.run_decision(status(), []), 'completed')
        for outer, command in [(1, 0), (0, 1), (None, 0), (0, None)]:
            with self.subTest(outer=outer, command=command), self.assertRaises(H.Stopped):
                H.run_decision(status(code=outer, command_code=command), [])

    def test_failed_actual_stage_never_becomes_wait_or_retry(self):
        for live in [[], [IDENTITY]]:
            with self.subTest(live=live), self.assertRaises(H.Stopped):
                H.run_decision(status('stopped', code=1, command_code=1), live)
        with self.assertRaises(H.Stopped):
            H.run_decision(status('stopped', code=1, command_code=0), [])

    def test_active_requires_exactly_one_live_controller(self):
        for phase in ['preflight', 'command']:
            self.assertEqual(H.run_decision(status(phase), [IDENTITY]), 'wait')
            for live in [[], [IDENTITY, IDENTITY]]:
                with self.subTest(phase=phase, live=live), self.assertRaises(H.Stopped):
                    H.run_decision(status(phase), live)
        with self.assertRaises(H.Stopped):
            H.run_decision(status('unrecognized'), [IDENTITY])

    def test_real_file_lock_blocks_duplicate_and_keeps_inode(self):
        path = self.root / 'test-only.lock'
        first = H.acquire_lock(path)
        self.addCleanup(first.close)
        inode = path.stat().st_ino
        with self.assertRaises(H.Stopped):
            H.acquire_lock(path)
        first.close()
        with H.acquire_lock(path):
            self.assertEqual(path.stat().st_ino, inode)

    def test_symlink_lock_is_rejected(self):
        target = self.root / 'target'
        target.write_text('unchanged')
        link = self.root / 'link.lock'
        link.symlink_to(target)
        with self.assertRaises(H.Stopped):
            H.acquire_lock(link)
        self.assertEqual(target.read_text(), 'unchanged')

    def test_session_logs_are_unique_and_existing_logs_unchanged(self):
        first = self.session()
        first.say('first preserved marker')
        before = (first.directory / 'stdout.log').read_bytes()
        second = self.session()
        self.assertNotEqual(first.directory, second.directory)
        self.assertEqual((first.directory / 'stdout.log').read_bytes(), before)
        self.assertIs(first.state['git_upload'], False)

    def test_wait_existing_job_without_spawning_or_signalling(self):
        session = self.session()
        path = self.root / 'fake-status.json'
        with mock.patch.object(H, 'read_json', side_effect=[status('command'), status('command'), status()]), \
             mock.patch.object(H, 'controllers', return_value=[dict(IDENTITY)]), \
             mock.patch.object(H.os, 'kill', side_effect=AssertionError('No signal allowed')):
            result = session.wait_run(path)
        self.assertEqual(result['phase'], 'completed')
        self.assertEqual(H.time.sleep.call_args_list, [mock.call(15), mock.call(15)])
        self.forbid_popen.assert_not_called()
        self.forbid_run.assert_not_called()

    def test_wait_detects_pid_reuse_or_controller_replacement(self):
        session = self.session()
        changed = dict(IDENTITY, start_ticks=3333)
        with mock.patch.object(H, 'read_json', return_value=status('command')), \
             mock.patch.object(H, 'controllers', side_effect=[[dict(IDENTITY)], [changed]]), \
             self.assertRaises(H.Stopped):
            session.wait_run(self.root / 'fake-status.json')

    def test_previous_refuses_failed_stale_and_duplicate_records(self):
        session = self.session()
        path = self.worker_record(value=status('stopped', code=1, command_code=1))
        with self.assertRaises(H.Stopped):
            session.previous('stage')
        path.write_text(json.dumps(status('command')))
        with self.assertRaises(H.Stopped):
            session.previous('stage')
        path.write_text(json.dumps(status()))
        self.worker_record('run-two')
        with self.assertRaises(H.Stopped):
            session.previous('stage')

    def test_no_record_with_live_controller_is_not_new_work(self):
        session = self.session()
        with mock.patch.object(H, 'controllers', return_value=[dict(IDENTITY)]), self.assertRaises(H.Stopped):
            session.previous('stage')

    def test_orphan_terminal_stage_without_runner_status_fails_closed(self):
        session = self.session()
        orphan = self.base / 'terminal-runs' / 'old-session' / 'stage-stage'
        orphan.mkdir(parents=True)
        (orphan / 'command.json').write_text(json.dumps({'argv': ['fake-runner'], 'process': IDENTITY}))
        (orphan / 'result.json').write_text(json.dumps({'exit_code': 1, 'process': IDENTITY}))
        with mock.patch.object(H, 'process_identity', return_value=None), self.assertRaises(H.Stopped):
            session.previous('stage')

    def test_recorded_live_launch_waits_for_first_status_instead_of_spawning(self):
        session = self.session()
        launch = self.base / 'terminal-runs' / 'old-session' / 'stage-stage'
        launch.mkdir(parents=True)
        (launch / 'command.json').write_text(json.dumps({'process': IDENTITY}))
        with mock.patch.object(H.time, 'sleep', side_effect=lambda _: self.worker_record()):
            result = session.previous('stage')
        self.assertEqual(result, self.base / 'runs/run-one')
        self.forbid_popen.assert_not_called(); self.forbid_run.assert_not_called()

    def test_recorded_live_launch_without_status_times_out_without_killing(self):
        session = self.session()
        launch = self.base / 'terminal-runs' / 'old-session' / 'stage-stage'
        launch.mkdir(parents=True)
        (launch / 'command.json').write_text(json.dumps({'process': IDENTITY}))
        with mock.patch.object(H.time, 'monotonic', side_effect=[0, 61]), \
             mock.patch.object(H.os, 'kill', side_effect=AssertionError('No signal allowed')), self.assertRaises(H.Stopped):
            session.previous('stage')
        self.forbid_popen.assert_not_called()

    def test_exact_environment_baseline_allows_only_pinned_flash_addition(self):
        session = self.session()
        baseline = {'torch': '2.7.1+cu128', 'torchvision': '0.22.1+cu128', 'numpy': '1.26.4'}
        (self.base / 'terminal-environment-baseline.json').write_text(json.dumps({'distributions': baseline}))

        def distributions(values):
            return [mock.Mock(metadata={'Name': name}, version=version) for name, version in values.items()]

        for index, good in enumerate([baseline, dict(baseline, **{'flash-attn': '2.8.3'})]):
            with mock.patch.object(H.md, 'distributions', return_value=distributions(good)):
                self.assertEqual(session.versions('good-' + str(index) + '.json'), good)
        bad_values = [dict(baseline, numpy='2.0.0'), dict(baseline, extra='1.0'),
                      {k: v for k, v in baseline.items() if k != 'numpy'},
                      dict(baseline, **{'flash-attn': '2.8.2'})]
        for bad in bad_values:
            with self.subTest(bad=bad), mock.patch.object(H.md, 'distributions', return_value=distributions(bad)), self.assertRaises(H.Stopped):
                session.versions('must-not-be-written.json')
        self.assertFalse((session.directory / 'must-not-be-written.json').exists())

    def test_success_stage_writes_live_streams_and_version_evidence(self):
        session = self.session()
        process = mock.Mock(pid=12345, returncode=0)
        process.poll.side_effect = [None, 0]
        observed = {}

        def fake_start(argv, **kwargs):
            self.assertTrue(kwargs['start_new_session'])
            self.assertEqual(kwargs['stdin'], H.subprocess.DEVNULL)
            kwargs['stdout'].write(b'live stdout\n'); kwargs['stdout'].flush()
            kwargs['stderr'].write(b'live stderr\n'); kwargs['stderr'].flush()
            observed['out'] = Path(kwargs['stdout'].name).read_bytes()
            observed['err'] = Path(kwargs['stderr'].name).read_bytes()
            return process

        with mock.patch.object(H.subprocess, 'Popen', side_effect=fake_start), \
             mock.patch.object(session, 'versions', return_value={}) as versions, \
             mock.patch.object(session, 'previous', return_value=self.root / 'completed-run'):
            session.run('stage', ['mock-executable'])
        self.assertEqual(observed, {'out': b'live stdout\n', 'err': b'live stderr\n'})
        self.assertEqual(versions.call_args_list, [mock.call('stage-versions-before.json'), mock.call('stage-versions-after.json')])
        record = json.loads((session.directory / 'stage-stage/result.json').read_text())
        self.assertEqual(record['exit_code'], 0)
        self.assertEqual(record['process'], IDENTITY)
        process.terminate.assert_not_called(); process.kill.assert_not_called()

    def test_interrupt_detaches_worker_without_killing(self):
        session = self.session()
        process = mock.Mock(pid=12345, returncode=None)
        process.poll.side_effect = KeyboardInterrupt
        with mock.patch.object(H.subprocess, 'Popen', return_value=process), \
             mock.patch.object(session, 'versions', return_value={}), self.assertRaises(KeyboardInterrupt):
            session.run('stage', ['mock-executable'])
        record = json.loads((session.directory / 'stage-stage/result.json').read_text())
        self.assertTrue(record['detached_on_interrupt'])
        self.assertIsNone(record['exit_code'])
        process.terminate.assert_not_called(); process.kill.assert_not_called(); process.send_signal.assert_not_called()

    def test_actual_nonzero_stage_is_logged_and_stops(self):
        session = self.session()
        process = mock.Mock(pid=12345, returncode=7)
        process.poll.return_value = 7
        with mock.patch.object(H.subprocess, 'Popen', return_value=process), \
             mock.patch.object(session, 'versions', return_value={}), \
             mock.patch.object(session, 'previous') as previous, self.assertRaises(H.Stopped):
            session.run('stage', ['mock-executable'])
        previous.assert_not_called()
        record = json.loads((session.directory / 'stage-stage/result.json').read_text())
        self.assertEqual(record['exit_code'], 7)
        self.assertEqual(session.state['stages'][0]['state'], 'stopped')

    def test_completed_example_never_respawns_or_selects_gpu(self):
        session = self.session()
        complete = {label: self.root / label for label in H.TERMINAL_LABELS}
        with mock.patch.object(H, 'wait_wheel_receipt', return_value=self.root / 'verified.whl'), \
             mock.patch.object(session, 'versions', return_value={'flash-attn': '2.8.3'}), \
             mock.patch.object(session, 'previous', side_effect=lambda label: complete[label]), \
             mock.patch.object(session, 'run', side_effect=AssertionError('Completed stage must not respawn')), \
             mock.patch.object(H, 'choose_gpu', side_effect=AssertionError('Completed example needs no GPU')), \
             mock.patch.object(H, 'checked_gpu_from_run', return_value=H.GPUS[0]), \
             mock.patch.object(H, 'verify_validation_binding', return_value=self.root / 'validation.json'), \
             mock.patch.object(H, 'execution_record', return_value=(self.root / 'execution.json', {'output_files_directory': str(self.root / 'outputs')})):
            H.continue_work(session)
        self.assertEqual(session.state['status'], 'completed')

    def test_bad_completed_install_version_never_reinstalls(self):
        session = self.session()
        with mock.patch.object(H, 'wait_wheel_receipt', return_value=self.root / 'verified.whl'), \
             mock.patch.object(session, 'versions', return_value={'flash-attn': 'wrong'}), \
             mock.patch.object(session, 'previous', return_value=self.root / 'previous'), \
             mock.patch.object(session, 'run', side_effect=AssertionError('No reinstall permitted')), self.assertRaises(H.Stopped):
            H.continue_work(session)

    def test_plan_does_not_create_session_or_spawn(self):
        output = io.StringIO()
        with mock.patch.object(H.sys, 'argv', [str(SOURCE)]), \
             mock.patch.object(H, 'Session', side_effect=AssertionError('Plan must not write')), \
             contextlib.redirect_stdout(output):
            self.assertEqual(H.main(), 0)
        value = json.loads(output.getvalue())
        self.assertFalse(value['executed'])
        self.assertFalse(value['automatic_git_upload'])
        self.assertFalse(value['automatic_download_or_rebuild'])
        self.forbid_popen.assert_not_called(); self.forbid_run.assert_not_called()

    def gpu_fixture(self, gpu=None):
        gpu = dict(gpu or H.GPUS[0])
        run = self.root / 'smoke-run'
        run.mkdir(exist_ok=True)
        fields = {'gpu_uuid': gpu['uuid'], 'gpu_index': gpu['index'], 'device_minor': gpu['minor']}
        (run / 'status.json').write_text(json.dumps(dict(status(label='terminal-flash-smoke'), **fields)))
        (run / 'plan.json').write_text(json.dumps(fields))
        return run

    def test_restores_exact_previously_tested_gpu(self):
        for gpu in H.GPUS:
            with self.subTest(gpu=gpu):
                self.assertEqual(H.checked_gpu_from_run(self.gpu_fixture(gpu)), gpu)

    def test_gpu_restore_rejects_unknown_uuid_and_inconsistent_mapping(self):
        for filename, key, value in [('status.json', 'gpu_uuid', 'GPU-unknown'),
                                     ('status.json', 'gpu_index', 99),
                                     ('status.json', 'device_minor', 99),
                                     ('plan.json', 'gpu_uuid', H.GPUS[1]['uuid']),
                                     ('plan.json', 'gpu_index', 99),
                                     ('plan.json', 'device_minor', 99)]:
            run = self.gpu_fixture()
            path = run / filename
            changed = json.loads(path.read_text()); changed[key] = value
            path.write_text(json.dumps(changed))
            with self.subTest(filename=filename, key=key), self.assertRaises(H.Stopped):
                H.checked_gpu_from_run(run)

    def test_continuation_checks_occupancy_only_on_previously_tested_gpu(self):
        session = self.session()
        previous = {label: self.root / label for label in H.TERMINAL_LABELS}
        previous['official-table'] = None
        gpu = H.GPUS[1]
        with mock.patch.object(H, 'wait_wheel_receipt', return_value=self.root / 'verified.whl'), \
             mock.patch.object(session, 'versions', return_value={'flash-attn': '2.8.3'}), \
             mock.patch.object(session, 'previous', side_effect=previous.get), \
             mock.patch.object(H, 'checked_gpu_from_run', return_value=gpu), \
             mock.patch.object(H, 'choose_gpu', return_value=gpu) as choose, \
             mock.patch.object(session, 'run', return_value=self.root / 'example-run') as run, \
             mock.patch.object(H, 'execution_record', return_value=(self.root / 'execution.json', {'output_files_directory': str(self.root / 'outputs')})), \
             mock.patch.object(H, 'verify_validation_binding', return_value=self.root / 'validation.json'):
            H.continue_work(session)
        choose.assert_called_once_with(session, candidates=[gpu])
        run.assert_called_once()
        label, argv = run.call_args.args
        self.assertEqual(label, 'official-table')
        self.assertEqual(argv[argv.index('--gpu-uuid') + 1], gpu['uuid'])

    def test_busy_previously_tested_gpu_does_not_fallback_or_infer(self):
        session = self.session()
        previous = {label: self.root / label for label in H.TERMINAL_LABELS}
        previous['official-table'] = None
        with mock.patch.object(H, 'wait_wheel_receipt', return_value=self.root / 'verified.whl'), \
             mock.patch.object(session, 'versions', return_value={'flash-attn': '2.8.3'}), \
             mock.patch.object(session, 'previous', side_effect=previous.get), \
             mock.patch.object(H, 'checked_gpu_from_run', return_value=H.GPUS[0]), \
             mock.patch.object(H, 'choose_gpu', side_effect=H.Stopped('Busy')) as choose, \
             mock.patch.object(session, 'run', side_effect=AssertionError('Busy GPU must not run')), self.assertRaises(H.Stopped):
            H.continue_work(session)
        choose.assert_called_once_with(session, candidates=[H.GPUS[0]])

    def validation_fixture(self):
        example = self.base / 'runs/example'
        example.mkdir(parents=True)
        (example / 'status.json').write_text(json.dumps(status(label='official-table')))
        validation = self.base / 'runs/validation'
        validation.mkdir(parents=True)
        output = self.root / 'outputs/example'
        output.mkdir(parents=True)
        artifact = output / 'fixture.txt'
        artifact.write_bytes(b'verified output fixture')
        report_path = self.base / 'validation-report.json'
        report = {'status': 'passed', 'exit_code': 0, 'output_directory': str(output),
                  'all_output_files': [{'path': str(artifact.relative_to(self.root)), 'size_bytes': artifact.stat().st_size}],
                  'checks': {'provenance': {'status': 'passed', 'result': {'execution_status': {
                      'path': str((example / 'status.json').relative_to(self.root)),
                      'sha256': H.digest(example / 'status.json')}}}}}
        report_path.write_text(json.dumps(report))
        command = H.target('validate_example_outputs.py', '--execute', '--output-dir', output,
                           '--execution-status', example / 'status.json', '--report', report_path)
        (validation / 'plan.json').write_text(json.dumps({'command': command}))
        return validation, example, output, report_path

    def test_existing_validator_report_is_bound_to_exact_example_and_output(self):
        validation, example, output, report = self.validation_fixture()
        self.assertEqual(H.verify_validation_binding(validation, example, output), report)
        (example / 'status.json').write_text(json.dumps(dict(status(label='official-table'), changed=True)))
        with self.assertRaises(H.Stopped):
            H.verify_validation_binding(validation, example, output)

    def test_validator_rejects_other_example_command(self):
        validation, example, output, report = self.validation_fixture()
        plan_path = validation / 'plan.json'
        plan = json.loads(plan_path.read_text())
        plan['command'][plan['command'].index('--execution-status') + 1] = str(self.root / 'different/status.json')
        plan_path.write_text(json.dumps(plan))
        with self.assertRaises(H.Stopped):
            H.verify_validation_binding(validation, example, output)

    def test_validator_rejects_missing_empty_outside_or_resized_artifacts(self):
        validation, example, output, report_path = self.validation_fixture()
        original = report_path.read_text()
        outside = self.root / 'outside.txt'
        outside.write_bytes(b'verified output fixture')
        for variant in ['empty', 'missing', 'outside', 'resized']:
            report = json.loads(original)
            if variant == 'empty':
                report['all_output_files'] = []
            elif variant == 'missing':
                report['all_output_files'][0]['path'] = str((output / 'missing.txt').relative_to(self.root))
            elif variant == 'outside':
                report['all_output_files'][0]['path'] = str(outside.relative_to(self.root))
            else:
                report['all_output_files'][0]['size_bytes'] += 1
            report_path.write_text(json.dumps(report))
            with self.subTest(variant=variant), self.assertRaises(H.Stopped):
                H.verify_validation_binding(validation, example, output)

    def test_validator_rejects_failed_report_wrong_output_and_wrong_evidence(self):
        validation, example, output, path = self.validation_fixture()
        original = path.read_text()
        for variant in ['failed', 'wrong-output', 'bad-provenance', 'wrong-status-path', 'wrong-status-hash']:
            report = json.loads(original)
            if variant == 'failed':
                report['status'] = 'failed'
            elif variant == 'wrong-output':
                report['output_directory'] = str(self.root / 'other-output')
            elif variant == 'bad-provenance':
                report['checks']['provenance']['status'] = 'failed'
            else:
                key = 'path' if variant == 'wrong-status-path' else 'sha256'
                report['checks']['provenance']['result']['execution_status'][key] = 'wrong'
            path.write_text(json.dumps(report))
            with self.subTest(variant=variant), self.assertRaises(H.Stopped):
                H.verify_validation_binding(validation, example, output)

    def wheel_receipt_fixture(self, destination):
        wheel = self.root / 'cache/wheels/flash-attention/fake-fixture.whl'
        wheel.parent.mkdir(parents=True, exist_ok=True)
        wheel.write_bytes(b'fixture only; never installed or imported')
        receipt = {'version': '2.8.3', 'source_commit': '060c9188beec3a8b62b33a3bfa6d5d2d44975fab',
                   'fetched_source_preserved': True, 'original_build_source_unmodified': True,
                   'wheel': str(wheel), 'wheel_size': wheel.stat().st_size, 'wheel_sha256': H.digest(wheel)}
        destination.mkdir(parents=True, exist_ok=True)
        (destination / 'result.json').write_text(json.dumps(receipt))
        return wheel

    def test_missing_wheel_receipt_uses_only_static_inspector_in_unique_session(self):
        session = self.session()
        calls = []

        def fake_inspection(label, argv):
            calls.append((label, argv))
            self.assertEqual(label, 'terminal-flash-inspect')
            self.assertEqual(argv[argv.index('--profile') + 1], 'build')
            command = argv[argv.index('--') + 1:]
            self.assertEqual(command[:4], H.target('inspect_flash_wheel.py')[:4])
            destination = Path(command[command.index('--output-dir') + 1])
            self.assertEqual(destination, session.directory / 'flash-wheel-inspection')
            self.assertFalse(destination.exists())
            self.wheel_receipt_fixture(destination)
            return self.base / 'runs/fake-inspection'

        with mock.patch.object(session, 'previous', return_value=None), mock.patch.object(session, 'run', side_effect=fake_inspection):
            wheel = H.wait_wheel_receipt(session)
        self.assertEqual(len(calls), 1)
        self.assertTrue(wheel.is_file())
        self.assertFalse((self.base / 'flash-attention-build/result.json').exists())
        self.assertTrue((session.directory / 'flash-wheel-verified.json').exists())
        self.forbid_popen.assert_not_called(); self.forbid_run.assert_not_called()

    def test_existing_agent_wheel_receipt_is_reused_without_inspection(self):
        session = self.session()
        destination = self.base / 'flash-attention-build'
        wheel = self.wheel_receipt_fixture(destination)
        original = (destination / 'result.json').read_bytes()
        with mock.patch.object(session, 'previous', return_value=None), \
             mock.patch.object(session, 'run', side_effect=AssertionError('Do not repeat static inspection')):
            self.assertEqual(H.wait_wheel_receipt(session), wheel)
        self.assertEqual((destination / 'result.json').read_bytes(), original)

    def test_existing_terminal_inspection_receipt_is_reused_and_hash_checked(self):
        session = self.session()
        inspection = self.base / 'runs/old-inspection'
        inspection.mkdir()
        destination = self.base / 'old-session-inspection'
        wheel = self.wheel_receipt_fixture(destination)
        (inspection / 'plan.json').write_text(json.dumps({'command': H.target('inspect_flash_wheel.py', '--output-dir', destination)}))
        with mock.patch.object(session, 'previous', return_value=inspection), \
             mock.patch.object(session, 'run', side_effect=AssertionError('Do not repeat completed inspection')):
            self.assertEqual(H.wait_wheel_receipt(session), wheel)
            wheel.write_bytes(b'changed wheel')
            with self.assertRaises(H.Stopped):
                H.wait_wheel_receipt(session)

    def test_existing_workers_finish_before_missing_receipt_inspection(self):
        session = self.session()
        events = []
        dependencies = [self.root / 'build/status.json', self.root / 'download/status.json']
        with mock.patch.object(H, 'DEPENDENCIES', dependencies), \
             mock.patch.object(session, 'wait_run', side_effect=lambda path: events.append(path)), \
             mock.patch.object(H, 'wait_wheel_receipt', side_effect=H.Stopped('stop after ordering audit')) as receipt, \
             self.assertRaises(H.Stopped):
            H.continue_work(session)
        self.assertEqual(events, dependencies)
        receipt.assert_called_once_with(session)

    def test_inspector_output_override_preserves_default_receipt_and_refuses_reuse(self):
        spec = importlib.util.spec_from_file_location('inspector_under_test', SOURCE.with_name('inspect_flash_wheel.py'))
        inspector = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(inspector)
        base = self.root / 'logs/official-example-20260921'
        log = base / 'flash-attention-build'
        source, build, wheels = self.root / 'source', self.root / 'build', self.root / 'wheels'
        for path in [log, source, build, wheels]:
            path.mkdir(parents=True)
        for path in [source, build]:
            (path / 'source.txt').write_bytes(b'unchanged fixture source')
        (log / 'source-files.json').write_text(json.dumps([{'path': 'source.txt', 'sha256': H.digest(source / 'source.txt')}]))
        (log / 'result.json').write_text('{"existing_agent_receipt": true}\n')
        preserved = (log / 'result.json').read_bytes()
        wheel = wheels / 'fixture.whl'
        with zipfile.ZipFile(wheel, 'w') as package:
            package.writestr('flash_attn-2.8.3.dist-info/METADATA', 'Name: flash-attn\nVersion: 2.8.3\n')
            package.writestr('flash_attn-2.8.3.dist-info/WHEEL', 'Wheel-Version: 1.0\n')
            package.writestr('flash_attn_2_cuda.fixture.so', b'not executable fixture')
        run = base / 'runs/20260921-flash-attention-wheel-fixture'
        run.mkdir(parents=True)
        (run / 'status.json').write_text(json.dumps(status()))
        destination = base / 'new-static-inspection'
        with mock.patch.multiple(inspector, ROOT=self.root, LOG=log, SOURCE=source, BUILD=build, WHEELS=wheels), \
             mock.patch.object(inspector.sys if hasattr(inspector, 'sys') else sys, 'argv', ['inspect_flash_wheel.py', '--output-dir', str(destination)]):
            inspector.main()
            self.assertTrue((destination / 'result.json').exists())
            before = (destination / 'result.json').read_bytes()
            with self.assertRaises(FileExistsError):
                inspector.main()
        self.assertEqual((destination / 'result.json').read_bytes(), before)
        self.assertEqual((log / 'result.json').read_bytes(), preserved)


def record_tests():
    """Record this test run directly; internal workload subprocesses stay mocked."""
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:10]
    destination = REAL_ROOT / 'logs/official-example-20260921/terminal-preparation-tests' / stamp
    destination.mkdir(parents=True, exist_ok=False)
    paths = [Path(__file__), SOURCE, SOURCE.with_name('inspect_flash_wheel.py')]
    record = {'argv': [sys.executable, '-I', '-B', '-S', str(Path(__file__).resolve()), '--record-logs'],
              'cwd': str(Path.cwd()), 'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'source_hashes': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
              'stdout': 'stdout.log', 'stderr': 'stderr.log', 'direct_capture': True,
              'scope': 'Stdlib fixture/mock tests only; no actual install, build, GPU, network, model import, or live worker manipulation.'}
    (destination / 'command.json').write_text(json.dumps(record, indent=2) + '\n')
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    with (destination / 'stdout.log').open('x') as out, (destination / 'stderr.log').open('x') as err, \
         contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        result = unittest.TextTestRunner(stream=err, verbosity=2).run(suite)
    record.update(exit_code=0 if result.wasSuccessful() else 1, test_count=result.testsRun,
                  failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
                  ended_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (destination / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'exit_code': record['exit_code'], 'test_count': result.testsRun, 'logs': str(destination)}))
    return record['exit_code']


if __name__ == '__main__':
    if sys.argv[1:] == ['--record-logs']:
        raise SystemExit(record_tests())
    unittest.main(verbosity=2)
