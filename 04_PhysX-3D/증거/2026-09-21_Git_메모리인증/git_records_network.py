"""Fixed-repository fetch/push/remote-check with secret-free per-run logs."""
import datetime
import json
import os
from pathlib import Path
import re
import resource
import subprocess
import sys

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
REPO = ROOT / 'repro-records'
BASE = ROOT / 'logs/git-records-20260921'
REMOTE = 'https://github.com/hyun2277/-physx-repro-2026.git'
ENV = {'HOME': os.environ['HOME'], 'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
       'LC_ALL': 'C.UTF-8', 'TMPDIR': str(ROOT / 'tmp'),
       'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1',
       'GIT_TERMINAL_PROMPT': '0', 'GIT_ASKPASS': '/bin/false', 'SSH_ASKPASS': '/bin/false'}
GIT = ['/usr/bin/git', '-C', str(REPO), '-c', 'core.hooksPath=/dev/null',
       '-c', 'http.extraHeader=', '-c', 'http.followRedirects=false',
       '-c', 'http.proxy=', '-c', 'http.sslVerify=true']


def local(*args):
    return subprocess.check_output(GIT + list(args), env=ENV, cwd=REPO,
                                   stderr=subprocess.PIPE, text=True).strip()


def scrub(text):
    text = re.sub(r'github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9_]+', '[REDACTED]', text)
    text = re.sub(r'(?im)^.*(?:authorization|proxy-authorization):.*$', '[REDACTED AUTH HEADER]', text)
    return text


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.umask(0o077)
    if len(sys.argv) != 2 or sys.argv[1] not in ('fetch', 'push', 'verify'):
        raise SystemExit('Use fetch, push, or verify only.')
    action = sys.argv[1]
    assert local('rev-parse', '--show-toplevel') == str(REPO)
    assert local('symbolic-ref', '--short', 'HEAD') == 'main'
    assert local('remote', 'get-url', '--all', 'origin') == REMOTE
    assert local('remote', 'get-url', '--push', '--all', 'origin') == REMOTE
    expected_helper = '/usr/bin/python3 -I -B -S ' + str(BASE / 'physx_auth_session.py') + ' helper'
    helpers = subprocess.check_output(GIT + ['config', '--local', '--get-all', 'credential.helper'],
                                      env=ENV, cwd=REPO, text=True).splitlines()
    assert helpers == ['', expected_helper]
    assert local('config', '--local', '--get', 'credential.username') == 'hyun2277'
    assert local('config', '--local', '--get', 'credential.useHttpPath') == 'true'
    for commit in ('ebd8d8999536c0a9c0fa4e081a7e86204998263e', '4052f2934ca81a60c3ef05f9bb691929ef2fb4cf'):
        local('merge-base', '--is-ancestor', commit, 'HEAD')
    if action == 'push':
        assert not local('status', '--porcelain'), 'Worktree/index must be clean.'
        local('merge-base', '--is-ancestor', 'origin/main', 'HEAD')
        paths = local('diff', '--name-only', 'origin/main..HEAD').splitlines()
        # Use zero-delimited bytes below so Unicode quoting cannot hide a path.
        raw = subprocess.check_output(GIT + ['diff', '--name-only', '-z', 'origin/main..HEAD'], env=ENV, cwd=REPO)
        assert all(p.startswith(b'04_PhysX-3D/') for p in raw.split(b'\0') if p), 'Out-of-scope changes.'
    operations = {'fetch': ['fetch', '--no-tags', 'origin', 'refs/heads/main:refs/remotes/origin/main'],
                  'push': ['push', 'origin', 'HEAD:refs/heads/main'],
                  'verify': ['ls-remote', '--exit-code', 'origin', 'refs/heads/main']}
    argv = GIT + operations[action]
    start = datetime.datetime.now().astimezone()
    run = BASE / ('network-' + action + '-' + start.strftime('%Y%m%dT%H%M%S%f'))
    run.mkdir()
    command = {'argv': argv, 'cwd': str(REPO), 'started_at': start.isoformat(),
               'head_before': local('rev-parse', 'HEAD'), 'origin_main_before': local('rev-parse', 'origin/main'),
               'authentication': 'hyun2277 repository-only RAM helper; no credential captured', 'force': False}
    (run / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
    try:
        proc = subprocess.run(argv, env=ENV, cwd=REPO, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
        out, err, code = scrub(proc.stdout), scrub(proc.stderr), proc.returncode
        state = 'completed'
    except subprocess.TimeoutExpired as exc:
        out = scrub((exc.stdout or b'').decode(errors='replace') if isinstance(exc.stdout, bytes) else (exc.stdout or ''))
        err = scrub((exc.stderr or b'').decode(errors='replace') if isinstance(exc.stderr, bytes) else (exc.stderr or ''))
        code, state = None, 'timeout'
    end = datetime.datetime.now().astimezone()
    (run / 'stdout.log').write_text(out)
    (run / 'stderr.log').write_text(err)
    result = {'action': action, 'state': state, 'started_at': start.isoformat(), 'ended_at': end.isoformat(),
              'elapsed_seconds': (end - start).total_seconds(), 'exit_code': code,
              'head_after': local('rev-parse', 'HEAD'), 'origin_main_after': local('rev-parse', 'origin/main'),
              'log_directory': str(run), 'force': False}
    (run / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    (BASE / ('latest-network-' + action + '.json')).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if out:
        print(out, end='' if out.endswith('\n') else '\n')
    if err:
        print(err, end='' if err.endswith('\n') else '\n')
    return code if code is not None and code >= 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
