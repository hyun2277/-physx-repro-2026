"""Offline imports and bundled video decoder check; no model loading or GPU calls."""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
SITE = ROOT / 'envs/physxgen/lib/python3.10/site-packages'
assert os.environ.get('PHYSX_RUN_PROFILE') == 'build'
assert os.environ.get('CUDA_VISIBLE_DEVICES') == ''
assert not list(Path('/dev').glob('nvidia*'))
sys.path.insert(0, str(SITE))
modules = ['clip', 'utils3d.torch', 'imageio', 'matplotlib.pyplot', 'cv2', 'scipy.ndimage',
           'trimesh', 'xatlas', 'pyvista', 'pymeshfix', 'igraph', 'rembg', 'safetensors', 'imageio_ffmpeg']
for name in modules:
    module = importlib.import_module(name)
    print(json.dumps({'module': name, 'imported': True, 'file': module.__file__}), flush=True)
files = list((SITE / 'imageio_ffmpeg/binaries').glob('ffmpeg-linux-x86_64-*'))
assert len(files) == 1
args = [str(files[0]), '-version']
print(json.dumps({'decoder_command': args}), flush=True)
result = subprocess.run(args, check=False)
print(json.dumps({'decoder_exit_code': result.returncode}), flush=True)
raise SystemExit(result.returncode)
