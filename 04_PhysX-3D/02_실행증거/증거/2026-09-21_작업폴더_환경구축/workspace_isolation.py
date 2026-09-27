"""Launch a command with PHYSx-only persistent writes. Does not install anything."""
import os
from pathlib import Path
import pwd
import sys

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
PLAN = ROOT / 'logs/install-plan-20260921'
PYENV = ROOT / 'envs/physxgen'
CUDA = ROOT / 'toolchains/cuda-12.8.1'


def inside_root(path):
    path = Path(path)
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT):
        raise SystemExit(f'Outside-workspace path or symlink rejected: {path}')
    return path


def main():
    if ROOT.resolve() != ROOT:
        raise SystemExit('Workspace root must be the expected canonical directory')
    if len(sys.argv) < 2:
        raise SystemExit('Usage: python -I -B -S workspace_isolation.py COMMAND [ARG ...]')
    original_home = os.environ.get('HOME') or pwd.getpwuid(os.getuid()).pw_dir
    env = {
        'HOME': original_home,
        'USER': pwd.getpwuid(os.getuid()).pw_name,
        'LOGNAME': pwd.getpwuid(os.getuid()).pw_name,
        'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'TERM': 'dumb',
        'PHYSX_ROOT': str(ROOT), 'PHYSX_PLAN': str(PLAN),
        'PHYSX_PYENV': str(PYENV), 'PHYSX_CUDA': str(CUDA),
        'PATH': f'{PYENV}/bin:{CUDA}/bin:/usr/bin:/bin',
        'CONDA_PKGS_DIRS': str(ROOT / 'cache/conda'),
        'CONDA_ENVS_PATH': str(ROOT / 'envs'),
        'CONDARC': str(PLAN / 'preview.condarc'),
        'CONDA_AUTO_UPDATE_CONDA': 'false',
        'CONDA_NOTIFY_OUTDATED_CONDA': 'false',
        'CONDA_REPORT_ERRORS': 'false',
        'PIP_CACHE_DIR': str(ROOT / 'cache/pip'),
        'PIP_CONFIG_FILE': '/dev/null',
        'PIP_DISABLE_PIP_VERSION_CHECK': '1',
        'XDG_CACHE_HOME': str(ROOT / 'cache/xdg'),
        'XDG_CONFIG_HOME': str(ROOT / 'cache/xdg-config'),
        'XDG_DATA_HOME': str(ROOT / 'cache/xdg-data'),
        'XDG_STATE_HOME': str(ROOT / 'cache/xdg-state'),
        'XDG_RUNTIME_DIR': str(ROOT / 'tmp/runtime'),
        'TMPDIR': str(ROOT / 'tmp'), 'TMP': str(ROOT / 'tmp'), 'TEMP': str(ROOT / 'tmp'),
        'TORCH_HOME': str(ROOT / 'cache/torch'),
        'TORCH_EXTENSIONS_DIR': str(ROOT / 'build/torch-extensions'),
        'HF_HOME': str(ROOT / 'cache/huggingface'),
        'HF_HUB_CACHE': str(ROOT / 'cache/huggingface/hub'),
        'HF_ASSETS_CACHE': str(ROOT / 'cache/huggingface/assets'),
        'HF_XET_CACHE': str(ROOT / 'cache/huggingface/xet'),
        'HF_MODULES_CACHE': str(ROOT / 'cache/huggingface/modules'),
        'HF_DATASETS_CACHE': str(ROOT / 'cache/huggingface/datasets'),
        'HF_TOKEN_PATH': str(ROOT / 'cache/huggingface/token'),
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
        'PYTHONNOUSERSITE': '1',
        'CUDA_HOME': str(CUDA), 'CUDACXX': str(CUDA / 'bin/nvcc'),
        'CC': '/usr/bin/gcc-13', 'CXX': '/usr/bin/g++-13',
        'CUDAHOSTCXX': '/usr/bin/g++-13', 'NVCC_CCBIN': '/usr/bin/g++-13',
        'TORCH_CUDA_ARCH_LIST': '12.0', 'MAX_JOBS': '4',
        'CUDA_VISIBLE_DEVICES': '',
        'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
        'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.hooksPath',
        'GIT_CONFIG_VALUE_0': '/dev/null',
        'GIT_TEMPLATE_DIR': str(ROOT / 'cache/git-template-empty'),
        'GIT_TERMINAL_PROMPT': '0',
    }
    # Do not copy inherited compiler, Python, cache, proxy, or shell startup variables.
    paths = {Path(value) for value in env.values() if value.startswith(str(ROOT) + '/')}
    paths.discard(PLAN / 'preview.condarc')
    paths.discard(CUDA / 'bin/nvcc')
    paths.discard(ROOT / 'cache/huggingface/token')
    paths.discard(CUDA)
    paths.add(ROOT / 'tmp/shm')
    paths.add(ROOT / 'sources')
    paths.add(ROOT / 'outputs')
    for path in (PYENV, CUDA, PLAN / 'preview.condarc', ROOT / 'cache/huggingface/token'):
        inside_root(path)
    # PATH is a path list, not a filesystem directory.
    paths = {path for path in paths if ':' not in str(path)}
    for path in sorted(paths):
        inside_root(path).mkdir(parents=True, exist_ok=True, mode=0o700)
    if any((ROOT / 'cache/git-template-empty').iterdir()):
        raise SystemExit('Git template directory must stay empty')
    argv = [
        '/usr/bin/bwrap', '--die-with-parent', '--new-session',
        '--unshare-user', '--unshare-pid', '--unshare-ipc', '--unshare-uts',
        '--cap-drop', 'ALL', '--clearenv',
        '--ro-bind', '/', '/', '--bind', str(ROOT), str(ROOT),
        '--bind', str(ROOT / 'tmp'), '/tmp',
        '--bind', str(ROOT / 'tmp'), '/var/tmp',
        '--proc', '/proc', '--ro-bind', '/proc/sys', '/proc/sys',
        '--dev', '/dev', '--bind', str(ROOT / 'tmp/shm'), '/dev/shm',
        '--chdir', str(ROOT),
    ]
    for key, value in env.items():
        argv += ['--setenv', key, value]
    argv += ['--'] + sys.argv[1:]
    # bwrap itself must not inherit loader overrides before --clearenv takes effect.
    os.execve(argv[0], argv, {
        'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
    })


if __name__ == '__main__':
    main()
