"""Pure plan tests. Never runs bwrap, NVIDIA tools, torch, or GPU operations."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent


def load(name):
    specification = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


launcher = load('gpu_check_launcher')
smoke = load('pytorch_smoke_check')
FAKE_UUID = 'GPU-00000000-1111-2222-3333-444444444444'


class PreparationTests(unittest.TestCase):
    def test_default_is_plan_and_cannot_dispatch_execute(self):
        output = io.StringIO()
        with patch.object(launcher, 'execute', side_effect=AssertionError('execute called')), contextlib.redirect_stdout(output):
            self.assertEqual(launcher.main([]), 0)
        data = json.loads(output.getvalue())
        self.assertEqual(data['mode'], 'plan')
        self.assertFalse(data['executed'])
        self.assertNotIn('torch', sys.modules)

    def test_smoke_default_cannot_dispatch_execute(self):
        output = io.StringIO()
        with patch.object(smoke, 'execute', side_effect=AssertionError('execute called')), contextlib.redirect_stdout(output):
            self.assertEqual(smoke.main([]), 0)
        self.assertFalse(json.loads(output.getvalue())['torch_imported'])

    def test_complete_uuid_required(self):
        for invalid in ('0', 'all', 'GPU-0000', FAKE_UUID + ',GPU-other'):
            with self.assertRaises(launcher.CheckStopped):
                launcher.plan(invalid, 0)

    def test_selected_node_only_and_network_isolation(self):
        data = launcher.plan(FAKE_UUID, 1)
        command = data['planned_smoke_argv']
        nodes = [command[i + 1] for i, part in enumerate(command) if part == '--dev-bind']
        self.assertEqual(nodes, ['/dev/nvidia1', '/dev/nvidiactl', '/dev/nvidia-uvm'])
        self.assertNotIn('/dev/nvidia0', command)
        self.assertIn('--unshare-net', command)
        self.assertIn('--clearenv', command)

    def test_dangerous_inherited_environment_omitted(self):
        dirty = {'HOME': '/home/minsujo', 'LD_LIBRARY_PATH': '/usr/local/cuda/lib64/stubs',
                 'GH_TOKEN': 'fake-test-value', 'SSH_AUTH_SOCK': '/tmp/not-an-agent',
                 'CUDA_VISIBLE_DEVICES': 'all', 'PYTHONPATH': '/tmp/untrusted',
                 'HTTP_PROXY': 'http://not-used'}
        with patch.dict(os.environ, dirty, clear=True):
            env = launcher.environment(FAKE_UUID, launcher.ROOT / 'tmp/fake-test-only')
        self.assertEqual(env['HOME'], dirty['HOME'])
        self.assertEqual(env['CUDA_VISIBLE_DEVICES'], FAKE_UUID)
        for key in ('LD_LIBRARY_PATH', 'GH_TOKEN', 'SSH_AUTH_SOCK', 'PYTHONPATH', 'HTTP_PROXY', 'CUDA_HOME'):
            self.assertNotIn(key, env)
        self.assertTrue(Path(env['TMPDIR']).is_relative_to(launcher.ROOT))

    def test_invalid_device_minor_rejected(self):
        for minor in (-1, 128, 255, '0', True):
            with self.assertRaises(launcher.CheckStopped):
                launcher.selected_nodes(minor)

    def test_runtime_paths_reject_system_cudart_and_driver_stubs(self):
        with self.assertRaises(RuntimeError):
            smoke.validate_runtime_paths({'libcudart.so': ['/usr/local/cuda-12.2/lib64/libcudart.so.12']})
        with self.assertRaises(RuntimeError):
            smoke.validate_runtime_paths({'libcuda.so': [str(launcher.TOOLKIT / 'lib/stubs/libcuda.so')]})
        with self.assertRaises(RuntimeError):
            smoke.validate_runtime_paths({}, require_complete=True)

    def test_usage_final_failure_preserves_successful_smoke(self):
        original = {'process_started': True, 'exit_code': 0, 'finished': 'original-finish'}
        result = launcher.failed_child_record(original, process_started=True, exit_code=0,
                                             error_name='CheckStopped')
        self.assertEqual(result, original)
        self.assertNotIn('interrupted', result)

    def test_launch_failure_and_actual_termination_are_distinct(self):
        launch = launcher.failed_child_record({'process_started': False}, process_started=False,
                                             exit_code=None, error_name='OSError')
        self.assertIsNone(launch['exit_code'])
        self.assertEqual(launch['launch_error'], 'OSError')
        self.assertNotIn('interrupted', launch)
        interrupted = launcher.failed_child_record({'process_started': True}, process_started=True,
                                                  exit_code=-15, error_name='CheckStopped', terminated=True)
        self.assertTrue(interrupted['interrupted'])
        self.assertTrue(interrupted['terminated'])
        self.assertEqual(interrupted['exit_code'], -15)

    def test_usage_fields_include_recording_requirements(self):
        required = {'memory.total', 'memory.used', 'utilization.gpu', 'temperature.gpu', 'power.draw'}
        self.assertTrue(required.issubset(launcher.DRIVER_QUERY_FIELDS.split(',')))
        self.assertTrue(required.issubset(launcher.USAGE_QUERY_FIELDS.split(',')))


if __name__ == '__main__':
    unittest.main()
