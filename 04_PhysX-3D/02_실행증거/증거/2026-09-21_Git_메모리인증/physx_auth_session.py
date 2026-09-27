"""Repository-scoped, eight-hour RAM credential session; standard library only.

Use /usr/bin/python3 -I -B -S SCRIPT login|status [--verify]|stop.
Only Git should invoke SCRIPT helper get|store|erase. Helper stdout is the secret
credential protocol: NEVER include that stream in console or general command
logging, and never run helper get or git credential fill as a status check.
Use the safe status command instead. FIFO checks prevent accidental direct
terminal output; they do NOT authenticate the caller or isolate same-UID
processes. Events contain only selected non-secret fields. Import does nothing.
"""
import datetime
import getpass
import json
import os
from pathlib import Path
import pwd
import re
import resource
import ssl
import stat
import subprocess
import sys
import urllib.error
import urllib.request
import warnings


ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
REPO = ROOT / 'repro-records'
LOGDIR = ROOT / 'logs/git-records-20260921'
SOCKET_DIR = ROOT / 'tmp/gh-hyun2277'
SOCKET = SOCKET_DIR / 'socket'
STATUS = LOGDIR / 'authsession-status.json'
EVENTS = LOGDIR / 'authsession.events.jsonl'
REMOTE = 'https://github.com/hyun2277/-physx-repro-2026.git'
ACCOUNT = 'hyun2277'
TTL = 28800
ANCESTORS = ('ebd8d8999536c0a9c0fa4e081a7e86204998263e',
             '4052f2934ca81a60c3ef05f9bb691929ef2fb4cf')
SCOPE = {'protocol': 'https', 'host': 'github.com',
         'path': 'hyun2277/-physx-repro-2026.git', 'username': ACCOUNT}


class SafeFailure(Exception):
    """Only fixed, non-sensitive error codes may be carried here."""


def ensure(condition, code):
    if not condition:
        raise SafeFailure(code)


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def child_environment():
    # Whitelist only. No inherited auth, Git tracing, proxy, TLS key logging,
    # loader/Python overrides, or debug variables enter the cache subprocess.
    return {
        'HOME': os.environ.get('HOME', pwd.getpwuid(os.getuid()).pw_dir),
        'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
        'TMPDIR': str(ROOT / 'tmp'), 'GIT_CONFIG_GLOBAL': '/dev/null',
        'GIT_CONFIG_NOSYSTEM': '1', 'GIT_TERMINAL_PROMPT': '0',
        'GIT_OPTIONAL_LOCKS': '0',
    }


def validate_paths():
    for path in (ROOT, REPO, LOGDIR, ROOT / 'tmp'):
        ensure(path.is_dir() and path.resolve() == path, 'unsafe_workspace_path')


def private_socket_directory(create=False):
    validate_paths()
    if not SOCKET_DIR.exists() and not SOCKET_DIR.is_symlink():
        if not create:
            return False
        SOCKET_DIR.mkdir(mode=0o700)
    data = SOCKET_DIR.lstat()
    ensure(stat.S_ISDIR(data.st_mode) and data.st_uid == os.getuid()
           and stat.S_IMODE(data.st_mode) == 0o700
           and SOCKET_DIR.resolve() == SOCKET_DIR, 'unsafe_socket_directory')
    if SOCKET.exists() or SOCKET.is_symlink():
        data = SOCKET.lstat()
        ensure(stat.S_ISSOCK(data.st_mode) and data.st_uid == os.getuid()
               and not (stat.S_IMODE(data.st_mode) & 0o077), 'unsafe_socket_file')
    return True


def safe_write(path, text, append=False):
    ensure(path.parent == LOGDIR and LOGDIR.resolve() == LOGDIR, 'unsafe_log_path')
    flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW
    flags |= os.O_APPEND if append else os.O_TRUNC
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        info = os.fstat(stream.fileno())
        ensure(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid(), 'unsafe_log_file')
        stream.write(text)


def event(phase, exit_code=0, **values):
    allowed = {'present', 'verified', 'user_id', 'expires_at', 'head', 'error_code',
               'repository_push_permission'}
    ensure(set(values).issubset(allowed), 'unsafe_event_field')
    record = {'timestamp': now().isoformat(), 'phase': phase,
              'exit_code': exit_code, 'account': ACCOUNT, **values}
    safe_write(EVENTS, json.dumps(record, sort_keys=True) + '\n', append=True)


def local_git(arguments, cwd=REPO):
    result = subprocess.run(
        ['/usr/bin/git', '--no-optional-locks', '-c', 'core.hooksPath=/dev/null',
         '-c', 'credential.helper=', *arguments], cwd=cwd, env=child_environment(),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8', errors='replace', timeout=15)
    ensure(result.returncode == 0, 'repository_check_failed')
    return result.stdout.strip()


def repository_head(require_history=True):
    ensure(local_git(['rev-parse', '--show-toplevel']) == str(REPO), 'wrong_repository')
    ensure(local_git(['config', '--get-all', 'remote.origin.url']) == REMOTE, 'wrong_origin')
    ensure(local_git(['symbolic-ref', '--short', 'HEAD']) == 'main', 'wrong_branch')
    head = local_git(['rev-parse', 'HEAD'])
    ensure(re.fullmatch('[0-9a-f]{40}', head) is not None, 'invalid_head')
    if require_history:
        for ancestor in ANCESTORS:
            local_git(['merge-base', '--is-ancestor', ancestor, head])
    return head


def helper_repository_scope():
    current = Path.cwd().resolve()
    ensure(current.is_relative_to(REPO), 'helper_wrong_directory')
    ensure(local_git(['rev-parse', '--show-toplevel'], cwd=current) == str(REPO),
           'helper_wrong_repository')


def cache(operation, token=None):
    ensure(operation in ('get', 'store', 'erase', 'exit'), 'invalid_cache_operation')
    if operation == 'store':
        ensure(isinstance(token, str) and token and not any(c in token for c in '\r\n\0'),
               'invalid_token_input')
    exists = private_socket_directory(create=operation == 'store')
    if not exists:
        return {}
    fields = dict(SCOPE)
    if operation == 'store':
        fields['password'] = token
    payload = ''.join(key + '=' + value + '\n' for key, value in fields.items()) + '\n'
    # The secret is only stdin here. Capture both streams; never pass them to
    # generic command logging, print exceptions, or use credential approve.
    result = subprocess.run(
        ['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-c', 'credential.helper=',
         'credential-cache', '--socket=' + str(SOCKET), '--timeout=' + str(TTL), operation],
        cwd=REPO, env=child_environment(), input='' if operation == 'exit' else payload,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding='utf-8', errors='strict', timeout=20)
    ensure(result.returncode == 0, 'cache_operation_failed')
    if operation != 'get':
        return {}
    ensure(len(result.stdout) <= 16384, 'invalid_cache_response')
    found = {}
    for line in result.stdout.splitlines():
        if not line:
            continue
        key, separator, value = line.partition('=')
        ensure(separator and key not in found, 'invalid_cache_response')
        found[key] = value
    if not found:
        return {}
    ensure(found.get('username') == ACCOUNT and found.get('password')
           and not any(c in found['password'] for c in '\r\n\0'), 'invalid_cache_response')
    return {'username': ACCOUNT, 'password': found['password']}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api(path, token):
    # Explicit verified context avoids create_default_context's SSLKEYLOGFILE
    # environment support. The token is never in a URL, argv, or environment.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_default_certs()
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect(),
        urllib.request.HTTPSHandler(context=context))
    request = urllib.request.Request('https://api.github.com' + path, headers={
        'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'physx-repo-ram-session',
    })
    try:
        with opener.open(request, timeout=30) as response:
            ensure(response.status == 200, 'github_unexpected_status')
            body = response.read(1024 * 1024 + 1)
        ensure(len(body) <= 1024 * 1024, 'github_response_too_large')
        data = json.loads(body)
        ensure(isinstance(data, dict), 'github_invalid_response')
        return data
    except urllib.error.HTTPError as error:
        if error.code in (401, 403, 404):
            raise SafeFailure('github_http_' + str(error.code)) from None
        raise SafeFailure('github_request_rejected') from None
    except (urllib.error.URLError, OSError, ValueError):
        raise SafeFailure('github_request_failed') from None


def verified_user(token):
    data = api('/user', token)
    ensure(data.get('login') == ACCOUNT, 'wrong_github_account')
    user_id = data.get('id')
    ensure(type(user_id) is int and user_id > 0, 'invalid_github_user_id')
    return user_id


def saved_status():
    if not STATUS.exists() and not STATUS.is_symlink():
        return {}
    info = STATUS.lstat()
    ensure(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
           and info.st_size <= 16384, 'unsafe_status_file')
    data = json.loads(STATUS.read_text())
    ensure(isinstance(data, dict) and data.get('account') == ACCOUNT, 'invalid_saved_status')
    return data


def login():
    ensure(sys.stdin.isatty(), 'interactive_terminal_required')
    head = repository_head()
    private_socket_directory(create=True)
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        try:
            token = getpass.getpass('hyun2277 GitHub PAT (표시·저장되지 않음): ')
        except getpass.GetPassWarning:
            raise SafeFailure('hidden_terminal_input_unavailable') from None
    ensure(token and not any(c in token for c in '\r\n\0'), 'invalid_token_input')
    store_attempted = False
    try:
        user_id = verified_user(token)
        repository = api('/repos/hyun2277/-physx-repro-2026', token)
        ensure(repository.get('full_name') == 'hyun2277/-physx-repro-2026', 'wrong_github_repository')
        permissions = repository.get('permissions', {})
        push_permission = isinstance(permissions, dict) and permissions.get('push') is True
        # A timed-out store may already have reached the daemon, so cleanup is
        # required once the attempt begins, not only after its successful exit.
        # Record expiry conservatively from before the store request.
        start = now()
        store_attempted = True
        cache('store', token)
        ensure(cache('get').get('password') == token, 'cache_store_verification_failed')
        data = {'account': ACCOUNT, 'user_id': user_id, 'login_verified': True,
                'verified_at': start.isoformat(), 'expires_at': (start + datetime.timedelta(seconds=TTL)).isoformat(),
                'ttl_seconds': TTL, 'head_at_login': head, 'state': 'active',
                'repository_push_permission': push_permission,
                'permission_note': 'Repository permission metadata does not establish PAT write grants.'}
        safe_write(STATUS, json.dumps(data, indent=2) + '\n')
        event('login', present=True, verified=True, user_id=user_id,
              expires_at=data['expires_at'], head=head, repository_push_permission=push_permission)
        return {'account': ACCOUNT, 'present': True, 'login_verified': True,
                'user_id': user_id, 'expires_at': data['expires_at'], 'head': head,
                'ttl_seconds': TTL, 'storage': 'RAM-only dedicated Git credential-cache',
                'repository_push_permission': push_permission,
                'permission_note': data['permission_note']}
    except BaseException:
        if store_attempted:
            try:
                cache('exit')
                ensure(not cache('get'), 'cache_not_empty_after_login_failure')
            except BaseException:
                raise SafeFailure('login_failed_cache_cleanup_unconfirmed') from None
        raise
    finally:
        token = ''


def status_command(verify=False):
    head = repository_head()
    entry = cache('get')
    data = saved_status()
    present = bool(entry)
    verified = False
    if verify and present:
        user_id = verified_user(entry['password'])
        ensure(data.get('user_id') == user_id, 'cached_identity_differs_from_login')
        verified = True
        data['verified_at'] = now().isoformat()
        safe_write(STATUS, json.dumps(data, indent=2) + '\n')
    entry.clear()
    result = {'account': ACCOUNT, 'present': present, 'head': head,
              'login_verified': bool(present and data.get('login_verified')),
              'verified_now': verified, 'expires_at': data.get('expires_at') if present else None,
              'state': 'present' if present else 'absent_or_expired'}
    event('status_verify' if verify else 'status', present=present, verified=verified, head=head)
    return result


def stop():
    cache('exit')
    ensure(not cache('get'), 'cache_not_empty_after_stop')
    data = saved_status()
    data.update(account=ACCOUNT, state='stopped', stopped_at=now().isoformat(), login_verified=False)
    safe_write(STATUS, json.dumps(data, indent=2) + '\n')
    event('stop', present=False, verified=False)
    return {'account': ACCOUNT, 'present': False, 'state': 'stopped',
            'git_configuration_restored': False, 'github_pat_revoked': False,
            'note': 'Only this dedicated RAM cache was stopped. Git configuration restoration and PAT revocation are separate actions.'}


def helper_quit():
    # This non-secret protocol directive prevents Git from falling back to a
    # different askpass/browser/terminal flow after cache miss or rejection.
    try:
        if stat.S_ISFIFO(os.fstat(1).st_mode):
            sys.stdout.write('quit=true\n\n')
            sys.stdout.flush()
    except OSError:
        pass


def helper(operation):
    ensure(operation in ('get', 'store', 'erase'), 'invalid_helper_operation')
    helper_repository_scope()
    ensure(stat.S_ISFIFO(os.fstat(0).st_mode), 'helper_stdin_must_be_git_pipe')
    if operation == 'get':
        # A FIFO is only an accidental terminal/log-output guard, not proof that
        # the caller is Git. Same-UID programs can create pipes and access cache.
        ensure(stat.S_ISFIFO(os.fstat(1).st_mode), 'helper_stdout_must_be_git_pipe')
    raw = sys.stdin.buffer.read(16385)
    ensure(len(raw) <= 16384, 'helper_input_too_large')
    fields = {}
    for line in raw.decode('utf-8', errors='strict').splitlines():
        if not line:
            break
        key, separator, value = line.partition('=')
        ensure(separator and key not in fields, 'invalid_helper_input')
        fields[key] = value
    ensure(all(fields.get(key) == value for key, value in SCOPE.items()), 'credential_scope_rejected')
    if operation == 'store':
        # Do not renew the eight-hour TTL when Git approves a successful request.
        event('helper_store_ignored')
        return
    if operation == 'erase':
        cache('erase')
        event('helper_erase', present=False)
        return
    entry = cache('get')
    event('helper_get', present=bool(entry))
    if entry:
        sys.stdout.write('username=' + ACCOUNT + '\npassword=' + entry['password'] + '\n\n')
        sys.stdout.flush()
    else:
        helper_quit()
    entry.clear()


def main():
    is_helper = len(sys.argv) > 1 and sys.argv[1] == 'helper'
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.umask(0o077)
        ensure(sys.flags.isolated and sys.flags.no_site, 'python_isolation_flags_required')
        validate_paths()
        if len(sys.argv) == 3 and is_helper:
            helper(sys.argv[2])
            return 0
        if sys.argv[1:] == ['login']:
            result = login()
        elif sys.argv[1:] in (['status'], ['status', '--verify']):
            result = status_command(verify=len(sys.argv) == 3)
        elif sys.argv[1:] == ['stop']:
            result = stop()
        else:
            raise SafeFailure('usage_login_status_verify_stop_or_git_helper')
        print(json.dumps(result, indent=2))
        return 0
    except BaseException as error:
        if isinstance(error, SafeFailure):
            code = str(error)
        elif isinstance(error, (KeyboardInterrupt, EOFError)):
            code = 'interactive_session_interrupted'
        elif isinstance(error, subprocess.TimeoutExpired):
            code = 'subprocess_timeout'
        else:
            code = 'local_operation_failed'
        try:
            event('helper_rejected' if is_helper else 'failed', exit_code=1, error_code=code)
        except Exception:
            pass
        # Never render raw exception messages, tracebacks, API bodies, cache output,
        # request headers, or user-supplied arguments (any might contain a token).
        if is_helper and sys.argv[1:3] == ['helper', 'get']:
            helper_quit()
        elif not is_helper:
            print(json.dumps({'account': ACCOUNT, 'exit_code': 1, 'error_code': code}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
