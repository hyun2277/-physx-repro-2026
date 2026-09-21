"""Tests use synthetic data/mocks only: no network, cache daemon or real secrets."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import types
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name('physx_auth_session.py')
spec = importlib.util.spec_from_file_location('session_under_test', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
SYNTHETIC = 'test-only-not-a-github-credential'


def tty_input():
    value = io.StringIO()
    value.isatty = lambda: True
    return value


def protocol_input(**changes):
    values = dict(m.SCOPE)
    values.update(changes)
    return types.SimpleNamespace(buffer=io.BytesIO(
        (''.join(k + '=' + v + '\n' for k, v in values.items()) + '\n').encode()))


class Checks(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.events = []
        self.writes = []
        self.stack.enter_context(patch.object(m, 'event', lambda *a, **k: self.events.append((a, k))))
        self.stack.enter_context(patch.object(m, 'safe_write', lambda *a, **k: self.writes.append((a, k))))
        self.stack.enter_context(patch.object(m, 'repository_head', return_value=m.ANCESTORS[-1]))
        self.stack.enter_context(patch.object(m, 'private_socket_directory', return_value=True))

    def login_mocks(self, cache):
        self.stack.enter_context(patch.object(m.sys, 'stdin', tty_input()))
        self.stack.enter_context(patch.object(m.getpass, 'getpass', return_value=SYNTHETIC))
        self.stack.enter_context(patch.object(m, 'verified_user', return_value=12345))
        self.stack.enter_context(patch.object(m, 'api', return_value={
            'full_name': 'hyun2277/-physx-repro-2026', 'permissions': {'push': True}}))
        self.stack.enter_context(patch.object(m, 'cache', side_effect=cache))

    def helper_mocks(self, **changes):
        self.stack.enter_context(patch.object(m, 'helper_repository_scope', return_value=None))
        self.stack.enter_context(patch.object(m.sys, 'stdin', protocol_input(**changes)))
        self.stack.enter_context(patch.object(m.os, 'fstat', return_value=types.SimpleNamespace(st_mode=stat.S_IFIFO)))

    def test_non_tty_login_stops_before_prompt(self):
        with patch.object(m.sys, 'stdin', io.StringIO()), patch.object(m.getpass, 'getpass') as prompt:
            with self.assertRaisesRegex(m.SafeFailure, 'interactive_terminal_required'):
                m.login()
            prompt.assert_not_called()

    def test_getpass_fallback_warning_stops(self):
        import warnings
        with patch.object(m.sys, 'stdin', tty_input()), patch.object(m.getpass, 'getpass', side_effect=lambda *a: warnings.warn('test', m.getpass.GetPassWarning)):
            with self.assertRaisesRegex(m.SafeFailure, 'hidden_terminal_input_unavailable'):
                m.login()

    def test_wrong_account_is_rejected(self):
        with patch.object(m, 'api', return_value={'login': 'sungmoon2', 'id': 123}):
            with self.assertRaisesRegex(m.SafeFailure, 'wrong_github_account'):
                m.verified_user(SYNTHETIC)

    def test_login_status_contains_no_credential(self):
        operations = []
        def cache(op, token=None):
            operations.append(op)
            return {'username': m.ACCOUNT, 'password': SYNTHETIC} if op == 'get' else {}
        self.login_mocks(cache)
        result = m.login()
        self.assertEqual(operations, ['store', 'get'])
        self.assertEqual(result['ttl_seconds'], 28800)
        self.assertNotIn(SYNTHETIC, str(result) + str(self.events) + str(self.writes))

    def test_store_failure_cleans_possible_partial_store(self):
        operations = []
        def cache(op, token=None):
            operations.append(op)
            if op == 'store':
                raise m.SafeFailure('synthetic_store_failure')
            return {}
        self.login_mocks(cache)
        with self.assertRaises(m.SafeFailure):
            m.login()
        self.assertIn('exit', operations)
        self.assertIn('get', operations)

    def test_helper_store_does_not_refresh_ttl(self):
        self.helper_mocks(password=SYNTHETIC)
        with patch.object(m, 'cache') as cache, contextlib.redirect_stdout(io.StringIO()) as out:
            m.helper('store')
            cache.assert_not_called()
        self.assertEqual(out.getvalue(), '')
        self.assertNotIn(SYNTHETIC, str(self.events))

    def test_cache_miss_quits_without_prompt_fallback(self):
        self.helper_mocks()
        with patch.object(m, 'cache', return_value={}), contextlib.redirect_stdout(io.StringIO()) as out:
            m.helper('get')
        self.assertEqual(out.getvalue(), 'quit=true\n\n')

    def test_wrong_scope_quits_and_never_reads_cache(self):
        self.helper_mocks(host='example.invalid')
        with patch.object(m, 'cache') as cache, patch.object(m.sys, 'argv', [str(SCRIPT), 'helper', 'get']), contextlib.redirect_stdout(io.StringIO()) as out:
            code = m.main()
            cache.assert_not_called()
        self.assertEqual(code, 1)
        self.assertEqual(out.getvalue(), 'quit=true\n\n')

    def test_status_does_not_output_cached_credential(self):
        with patch.object(m, 'cache', return_value={'username': m.ACCOUNT, 'password': SYNTHETIC}), patch.object(m, 'saved_status', return_value={'account': m.ACCOUNT, 'login_verified': True}):
            result = m.status_command()
        self.assertTrue(result['present'])
        self.assertNotIn(SYNTHETIC, str(result) + str(self.events))

    def test_stop_only_uses_dedicated_cache_exit_and_get(self):
        with patch.object(m, 'cache', return_value={}) as cache, patch.object(m, 'saved_status', return_value={}):
            result = m.stop()
        self.assertEqual([call.args[0] for call in cache.call_args_list], ['exit', 'get'])
        self.assertFalse(result['present'])
        self.assertFalse(result['github_pat_revoked'])

    def test_backend_secret_is_stdin_only_and_no_global_helper(self):
        with patch.object(m.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0, stdout='', stderr='')) as run:
            m.cache('store', SYNTHETIC)
        args, kwargs = run.call_args
        self.assertNotIn(SYNTHETIC, str(args) + str(kwargs['env']))
        self.assertIn(SYNTHETIC, kwargs['input'])
        self.assertIn('credential.helper=', args[0])
        self.assertIn('--socket=' + str(m.SOCKET), args[0])
        self.assertEqual(kwargs['env']['GIT_CONFIG_GLOBAL'], '/dev/null')


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
    print(json.dumps({'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
                      'passed': result.wasSuccessful(), 'real_credentials_used': False,
                      'network_or_real_cache_started': False}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
