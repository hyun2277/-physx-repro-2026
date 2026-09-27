"""One tiny GPU numerical check. Default mode is a non-executing JSON plan."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import re
import stat
import sys
import time


ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
ENV = ROOT / 'envs/physxgen'
SITE = ENV / 'lib/python3.10/site-packages'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def loaded_cuda_libraries():
    result = {}
    names = ('libcuda.so', 'libcudart.so', 'libcublas.so', 'libcublasLt.so', 'libtorch_cuda.so')
    for line in Path('/proc/self/maps').read_text().splitlines():
        parts = line.split(maxsplit=5)
        if len(parts) == 6 and parts[5].startswith('/'):
            path = Path(parts[5])
            for name in names:
                if path.name.startswith(name):
                    resolved = path.resolve(strict=True)
                    result.setdefault(name, set()).add(str(resolved))
    return {key: sorted(value) for key, value in result.items()}


def validate_runtime_paths(libraries, require_complete=False):
    for name in ('libcudart.so', 'libcublas.so', 'libcublasLt.so'):
        if require_complete:
            require(libraries.get(name), 'Expected loaded CUDA runtime library missing: ' + name)
        require(all(Path(p).is_relative_to(SITE) and '/stubs/' not in p
                    for p in libraries.get(name, [])),
                'A CUDA runtime library was loaded outside the approved Python environment: ' + name)
    require(all('/stubs/' not in p for p in libraries.get('libcuda.so', [])),
            'A driver stub library was loaded.')
    if require_complete:
        require(libraries.get('libcuda.so'), 'Real system driver library was not identified.')


def check_boundary(gpu_uuid, minor):
    require(sys.flags.isolated and sys.flags.no_site, 'The check requires -I -B -S.')
    require(Path(sys.prefix).resolve() == ENV, 'Wrong Python environment.')
    require(os.environ.get('PHYSX_GPU_CHECK_ISOLATED') == '1', 'Use the reviewed GPU launcher.')
    require(os.environ.get('CUDA_VISIBLE_DEVICES') == gpu_uuid, 'UUID visibility guard differs.')
    require(re.fullmatch(r'GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', gpu_uuid), 'Full GPU UUID required.')
    require(type(minor) is int and 0 <= minor < 128, 'Invalid device minor.')
    visible = sorted(str(p) for p in Path('/dev').iterdir() if re.fullmatch(r'nvidia\d+', p.name))
    require(visible == [f'/dev/nvidia{minor}'], 'Exactly the selected GPU character-node path must be visible.')
    for path in (f'/dev/nvidia{minor}', '/dev/nvidiactl', '/dev/nvidia-uvm'):
        require(stat.S_ISCHR(Path(path).stat().st_mode), 'Required character device unavailable.')
    for path in ('/usr/local', '/etc', '/home/minsujo', str(ENV), str(ROOT / 'toolchains/cuda-12.8.1')):
        require(os.statvfs(path).f_flag & os.ST_RDONLY, 'Expected read-only mount missing: ' + path)
    require(not (os.statvfs(ROOT).f_flag & os.ST_RDONLY), 'Workspace must be the writable output location.')
    forbidden = ('LD_LIBRARY_PATH', 'LD_PRELOAD', 'LD_AUDIT', 'PYTHONPATH', 'PYTHONHOME',
                 'CUDA_HOME', 'CUDACXX', 'SSH_AUTH_SOCK', 'HF_TOKEN', 'GITHUB_TOKEN',
                 'GH_TOKEN', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY')
    require(not any(key in os.environ for key in forbidden), 'Unexpected inherited loader/auth/proxy/compiler setting.')
    for key in ('TMPDIR', 'TORCH_HOME', 'TORCH_EXTENSIONS_DIR', 'CUDA_CACHE_PATH', 'XDG_CACHE_HOME'):
        require(Path(os.environ[key]).resolve().is_relative_to(ROOT), 'Cache/temp path escapes workspace: ' + key)
    versions = {d.metadata['Name'].lower(): d.version for d in importlib.metadata.distributions(path=[str(SITE)])}
    require(versions.get('torch') == '2.7.1+cu128' and versions.get('torchvision') == '0.22.1+cu128',
            'Installed wheel versions differ from the reviewed foundation.')


def execute(gpu_uuid, minor):
    check_boundary(gpu_uuid, minor)
    started = time.monotonic()
    # -S prevents .pth/sitecustomize execution; add only the approved site path.
    sys.path.insert(0, str(SITE))
    import torch
    import torchvision

    require(torch.__version__ == '2.7.1+cu128', 'Unexpected imported torch version.')
    require(torchvision.__version__ == '0.22.1+cu128', 'Unexpected imported torchvision version.')
    require(torch.version.cuda == '12.8', 'Unexpected PyTorch CUDA build.')
    # Check any already-loaded runtime paths before creating tensors/contexts,
    # then require all relevant libraries after cuBLAS has been exercised.
    validate_runtime_paths(loaded_cuda_libraries())
    require(torch.cuda.is_available(), 'CUDA is not available; no fallback.')
    require(torch.cuda.device_count() == 1, 'CUDA must expose exactly one logical device.')
    properties = torch.cuda.get_device_properties(0)
    capability = (properties.major, properties.minor)
    require(capability == (12, 0), 'This prepared RTX 5090 check expects compute capability 12.0.')
    require('sm_120' in torch.cuda.get_arch_list(), 'The imported PyTorch wheel lacks sm_120.')
    property_uuid = getattr(properties, 'uuid', None)
    if property_uuid is not None:
        normalized = str(property_uuid).lower().removeprefix('gpu-')
        require(normalized == gpu_uuid.lower().removeprefix('gpu-'), 'PyTorch GPU UUID differs from the selected UUID.')
    # One fixed-size FP32 workload: no model, compilation, training, or repetition.
    # Context/cuBLAS workspace memory is driver-managed and not included in the
    # <2 MiB explicit tensor bound. This is not a hardware memory quota.
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.set_grad_enabled(False)
    left = torch.ones((256, 256), dtype=torch.float32, device='cuda:0')
    right = torch.ones((256, 256), dtype=torch.float32, device='cuda:0')
    output = left @ right
    torch.cuda.synchronize(0)
    maximum_error = (output - 256.0).abs().max().item()
    require(maximum_error == 0.0, 'Numerical matrix-multiplication result differs.')
    torch.cuda.synchronize(0)
    libraries = loaded_cuda_libraries()
    validate_runtime_paths(libraries, require_complete=True)
    result = {
        'status': 'passed', 'torch': torch.__version__, 'torchvision': torchvision.__version__,
        'torch_cuda_build': torch.version.cuda, 'selected_gpu_uuid': gpu_uuid,
        'selected_device_minor': minor, 'logical_cuda_device': 0,
        'torch_device_uuid': str(property_uuid) if property_uuid is not None else None,
        'uuid_crosscheck': 'torch properties' if property_uuid is not None else 'launcher driver-proc mapping + selected character node + full UUID visibility',
        'device_name': properties.name, 'compute_capability': list(capability),
        'matrix_shape': [256, 256], 'dtype': 'float32', 'expected_value': 256.0,
        'maximum_absolute_error': maximum_error,
        'peak_tensor_allocation_bytes': torch.cuda.max_memory_allocated(0),
        'elapsed_seconds': time.monotonic() - started, 'loaded_cuda_libraries': libraries,
        'limit': 'This passes only a small PyTorch/torchvision GPU compatibility check; extensions and PhysX reproduction remain untested.',
    }
    print(json.dumps(result, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--gpu-uuid')
    parser.add_argument('--device-minor', type=int)
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({'mode': 'plan', 'executed': False, 'torch_imported': False,
                          'future_entrypoint': 'gpu_check_launcher.py --execute --gpu-uuid FULL_UUID --device-minor MINOR',
                          'check': 'one 256x256 FP32 CUDA matmul, synchronize, exact numerical result'}, indent=2))
        return 0
    try:
        require(args.gpu_uuid is not None and args.device_minor is not None, 'Explicit UUID/minor required.')
        execute(args.gpu_uuid, args.device_minor)
        return 0
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__, 'message': str(error)}, indent=2), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
