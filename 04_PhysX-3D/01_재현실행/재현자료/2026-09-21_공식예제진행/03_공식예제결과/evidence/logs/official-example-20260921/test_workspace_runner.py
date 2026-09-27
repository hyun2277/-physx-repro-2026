"""Pure preparation tests: never runs bwrap, compilers, GPU tools, or torch."""
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
spec = importlib.util.spec_from_file_location('workspace_runner', HERE / 'workspace_runner.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
GPU = 'GPU-00000000-1111-2222-3333-444444444444'


def arguments(profile, *extra):
    return runner.parse_args(['--profile', profile, '--label', 'test-only', *extra, '--', '/usr/bin/true'])


class PreparationTests(unittest.TestCase):
    def test_default_plan_no_execute(self):
        out = io.StringIO()
        with patch.object(runner, 'execute', side_effect=AssertionError('execution prohibited')), contextlib.redirect_stdout(out):
            self.assertEqual(runner.main(['--profile', 'build', '--label', 'mock', '--', '/usr/bin/true']), 0)
        self.assertFalse(json.loads(out.getvalue())['executed'])
        self.assertNotIn('torch', sys.modules)

    def test_profile_filesystem_and_network_boundaries(self):
        for profile in ('download', 'install', 'build'):
            args = arguments(profile)
            command = runner.bwrap_command(args, runner.ROOT / 'tmp/test-unused')
            self.assertEqual('--unshare-net' in command, profile != 'download')
            self.assertNotIn('--dev-bind', command)
            readonly = [command[i + 1] for i, part in enumerate(command) if part == '--ro-bind']
            self.assertIn(str(runner.TOOLKIT), readonly)
            self.assertEqual(str(runner.PYENV) in readonly, profile != 'install')

    def test_gpu_requires_full_explicit_identity(self):
        for selectors in ([], ['--gpu-uuid', GPU], ['--gpu-uuid', 'GPU-0000', '--gpu-index', '0', '--device-minor', '0']):
            with self.assertRaises(runner.Stopped):
                runner.plan(arguments('gpu', *selectors))
        with self.assertRaises(runner.Stopped):
            runner.plan(arguments('build', '--gpu-uuid', GPU))

    def test_gpu_only_selected_character_nodes(self):
        data = runner.plan(arguments('gpu', '--gpu-uuid', GPU, '--gpu-index', '1', '--device-minor', '1'))
        command = data['bwrap_argv']
        nodes = [command[i + 1] for i, part in enumerate(command) if part == '--dev-bind']
        self.assertEqual(nodes, ['/dev/nvidia1', '/dev/nvidiactl', '/dev/nvidia-uvm'])
        self.assertNotIn('/dev/nvidia0', command)
        self.assertIn('--unshare-net', command)

    def test_environment_does_not_inherit_credentials_or_loader(self):
        dirty = {'HOME': '/home/minsujo', 'GH_TOKEN': 'fake-test', 'LD_LIBRARY_PATH': '/cuda/stubs',
                 'SSLKEYLOGFILE': '/tmp/unsafe', 'SSH_AUTH_SOCK': '/tmp/unsafe', 'HTTP_PROXY': 'unused',
                 'PYTHONPATH': '/tmp/unsafe'}
        with patch.dict(os.environ, dirty, clear=True):
            env = runner.environment('gpu', GPU, runner.ROOT / 'tmp/test-unused')
        self.assertEqual(env['HOME'], dirty['HOME'])
        for key in dirty.keys() - {'HOME'}:
            self.assertNotIn(key, env)
        self.assertEqual(env['CUDA_VISIBLE_DEVICES'], GPU)
        self.assertEqual(env['CC'], '/usr/bin/gcc-13')
        self.assertEqual(env['TORCH_CUDA_ARCH_LIST'], '12.0')
        self.assertEqual(env['CPLUS_INCLUDE_PATH'], str(runner.TOOLKIT / 'targets/x86_64-linux/include'))
        self.assertEqual(env['LIBRARY_PATH'], str(runner.TOOLKIT / 'targets/x86_64-linux/lib'))
        self.assertEqual(env['HF_TOKEN_PATH'], '/dev/null')
        self.assertEqual(env['HF_HUB_OFFLINE'], '1')

    def test_gpu_query_identity_must_match(self):
        args = arguments('gpu', '--gpu-uuid', GPU, '--gpu-index', '1', '--device-minor', '1')
        text = f'1,{GPU},0000:01:00.0,Fake,580,32000,0,0,30,20,2099/01/01 00:00:00\n'
        self.assertEqual(runner.validate_gpu_row(text, args, host_preflight=True)['uuid'], GPU)
        with self.assertRaises(runner.Stopped):
            runner.validate_gpu_row(text.replace('1,', '0,', 1), args, host_preflight=True)
        with self.assertRaises(runner.Stopped):
            runner.validate_gpu_row(text + text, args, host_preflight=True)

    def test_isolated_index_remaps_to_zero_but_uuid_pci_must_match(self):
        args = arguments('gpu', '--gpu-uuid', GPU, '--gpu-index', '1', '--device-minor', '1')
        text = f'0,{GPU},00000000:02:00.0,Fake,580,32000,0,0,30,20,2099/01/01 00:00:00\n'
        result = runner.validate_gpu_row(text, args, expected_pci_bus_id='0000:02:00.0')
        self.assertEqual(result['index'], '0')
        for invalid in (text.replace('0,', '1,', 1), text.replace(GPU, GPU[:-1] + '5'),
                        text.replace('02:00.0', '03:00.0')):
            with self.assertRaises(runner.Stopped):
                runner.validate_gpu_row(invalid, args, expected_pci_bus_id='0000:02:00.0')
        with self.assertRaises(runner.Stopped):
            runner.validate_gpu_row(text, args)

    def test_host_preflight_query_is_fixed_and_selected_only(self):
        args = arguments('gpu', '--gpu-uuid', GPU, '--gpu-index', '1', '--device-minor', '1')
        for compute in (False, True):
            command = runner.gpu_query_command(args, compute)
            self.assertEqual(command[0], '/usr/bin/nvidia-smi')
            self.assertEqual(command[1], '--id=' + GPU)
            self.assertEqual(len(command), 4)
            self.assertEqual(command[-1], '--format=csv,noheader,nounits')
        workload = runner.bwrap_command(args, runner.ROOT / 'tmp/test-unused')
        self.assertIn('--unshare-pid', workload)

    def test_unsafe_paths_labels_and_auth_args_rejected(self):
        for changes in ({'cwd': Path('/tmp')}, {'label': '../bad'}, {'command': ['/usr/bin/curl', '--token=secret']},
                        {'command': ['python']}, {'timeout_seconds': 0}):
            args = arguments('download')
            for key, value in changes.items():
                setattr(args, key, value)
            with self.assertRaises(runner.Stopped):
                runner.plan(args)


if __name__ == '__main__':
    unittest.main()
