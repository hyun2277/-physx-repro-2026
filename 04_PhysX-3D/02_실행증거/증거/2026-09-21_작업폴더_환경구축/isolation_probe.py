"""Standard-library-only path/mount probe. No package or GPU initialization."""
import errno
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')


def readonly(path):
    return bool(os.statvfs(path).f_flag & os.ST_RDONLY)


outside = ['/usr/local', '/usr/local/cuda-12.2', '/home/minsujo',
           '/home/minsujo/anaconda3', '/etc', '/proc/sys']
external = {path: readonly(path) for path in outside}
assert all(external.values()), external
assert not readonly(ROOT)
paths = [ROOT / 'tmp', Path('/tmp'), Path('/var/tmp'), Path('/dev/shm')]
backing = [ROOT / 'tmp', ROOT / 'tmp', ROOT / 'tmp', ROOT / 'tmp/shm']
probes = []
for path, storage in zip(paths, backing):
    with tempfile.NamedTemporaryFile(prefix='physx-isolation-probe-', dir=path) as item:
        item.write(b'path-only probe\n')
        item.flush()
        expected = storage / Path(item.name).name
        assert expected.is_file() and expected.read_bytes() == b'path-only probe\n'
        probes.append({'visible_directory': str(path), 'workspace_storage': str(storage), 'verified': True})

# Opening this existing file without O_TRUNC writes no data even if isolation failed.
open_result = {}
try:
    fd = os.open('/etc/os-release', os.O_WRONLY)
except OSError as error:
    open_result = {
        'errno': error.errno,
        'errno_name': errno.errorcode.get(error.errno),
        'write_handle_denied': error.errno in (errno.EROFS, errno.EACCES, errno.EPERM),
        'mount_readonly_independently_checked': readonly('/etc/os-release'),
    }
else:
    os.close(fd)
    raise AssertionError('External path unexpectedly permits a write handle')
assert open_result['write_handle_denied'], open_result
assert open_result['mount_readonly_independently_checked'], open_result
unwanted = ['LD_LIBRARY_PATH', 'LD_PRELOAD', 'LD_AUDIT', 'PYTHONPATH', 'PYTHONHOME', 'BASH_ENV',
            'NVCC_PREPEND_FLAGS', 'NVCC_APPEND_FLAGS', 'CPATH', 'LIBRARY_PATH',
            'CMAKE_PREFIX_PATH', 'TRANSFORMERS_CACHE', 'PYTORCH_TRANSFORMERS_CACHE',
            'PYTORCH_PRETRAINED_BERT_CACHE', 'TRITON_CACHE_MANAGER', 'GIT_DIR', 'PIP_TARGET']
assert all(key not in os.environ for key in unwanted)
gpu_paths = list(Path('/dev').glob('nvidia*')) + list(Path('/dev').glob('dri*'))
assert not gpu_paths
git = subprocess.run(['/usr/bin/git', 'config', '--get', 'core.hooksPath'],
                     text=True, capture_output=True, check=True)
assert git.stdout.strip() == '/dev/null'
assert os.environ['HOME'] == '/home/minsujo'
cache_variables = [
    'CONDA_PKGS_DIRS', 'CONDA_ENVS_PATH', 'PIP_CACHE_DIR', 'TMPDIR', 'TMP', 'TEMP',
    'XDG_CACHE_HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_RUNTIME_DIR',
    'TORCH_HOME', 'TORCH_EXTENSIONS_DIR', 'HF_HOME', 'HF_HUB_CACHE', 'HF_ASSETS_CACHE',
    'HF_XET_CACHE', 'HF_MODULES_CACHE', 'HF_DATASETS_CACHE', 'HF_TOKEN_PATH', 'U2NET_HOME',
    'PHYSX_CLIP_DOWNLOAD_ROOT', 'CUDA_CACHE_PATH', 'TRITON_CACHE_DIR', 'TRITON_DUMP_DIR',
    'TRITON_OVERRIDE_DIR', 'NUMBA_CACHE_DIR', 'MPLCONFIGDIR', 'IMAGEIO_USERDIR',
    'PYTHONPYCACHEPREFIX', 'GIT_TEMPLATE_DIR',
]
for key in cache_variables:
    assert Path(os.environ[key]).resolve().is_relative_to(ROOT), key
print(json.dumps({
    'external_mounts_readonly': external,
    'workspace_write_and_temporary_aliases': probes,
    'external_write_handle_denied': open_result,
    'inherited_override_variables_absent': unwanted,
    'gpu_device_paths': [str(path) for path in gpu_paths],
    'git_hooks_path': git.stdout.strip(),
    'home_preserved': os.environ['HOME'],
    'cache_and_temporary_paths': {key: os.environ[key] for key in cache_variables},
    'limit': 'Mount/path/environment probe only; no install, build, model initialization, network, or GPU operation.',
}, indent=2))
