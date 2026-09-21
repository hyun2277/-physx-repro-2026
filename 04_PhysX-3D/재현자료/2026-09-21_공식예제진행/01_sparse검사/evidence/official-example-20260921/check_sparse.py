"""Plan or explicitly run two tiny pinned sparse-convolution checks.

No installation or source build. Only the parent-approved isolated GPU process
may use --execute. This file has not itself been run on a GPU during preparation.
"""
import argparse
import datetime
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sys
import time
import traceback
import uuid

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
ENV = ROOT / 'envs/physxgen'
SITE = ENV / 'lib/python3.10/site-packages'
RUN = ROOT / 'logs/official-example-20260921'
RESULT = RUN / 'sparse-check.result.json'
TRACEBACK = RUN / 'sparse-check.traceback.log'
EXPECTED = {'torch': '2.7.1+cu128', 'torchvision': '0.22.1+cu128',
            'spconv-cu126': '2.3.8', 'cumm-cu126': '0.7.11'}
COORDINATES = [[0, 0, 0, 0], [0, 1, 1, 1], [0, 1, 1, 2], [0, 1, 2, 1],
               [0, 2, 1, 1], [0, 2, 2, 2], [0, 3, 3, 3], [0, 4, 4, 4]]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def save(value):
    require(RUN.resolve() == RUN and RUN.is_relative_to(ROOT), 'Unsafe result directory.')
    require(not RESULT.is_symlink(), 'Result path may not be a symlink.')
    RESULT.write_text(json.dumps(value, indent=2) + '\n')


def mapped_libraries(query_nvrtc=False):
    """Observe mapped files; optional version calls use already-loaded handles."""
    rows = {}
    try:
        for line in Path('/proc/self/maps').read_text().splitlines():
            parts = line.split(maxsplit=5)
            if len(parts) != 6 or not parts[5].startswith('/'):
                continue
            path = Path(parts[5])
            filename = path.name
            kind = None
            for prefix, group in [('libnvrtc-builtins', 'nvrtc_builtins'), ('libnvrtc', 'nvrtc'),
                                  ('libcudart', 'cudart'), ('libcuda.so', 'driver'),
                                  ('libtorch_cuda', 'torch_cuda'), ('libcublas', 'cublas')]:
                if filename.startswith(prefix):
                    kind = group
                    break
            if 'core_cc' in filename and ('/spconv/' in str(path) or '/cumm/' in str(path)):
                kind = 'spconv_core' if '/spconv/' in str(path) else 'cumm_core'
            if kind is None:
                continue
            resolved = path.resolve()
            rows[str(resolved)] = {'kind': kind, 'path': str(path), 'resolved_path': str(resolved),
                                   'inside_python_environment': resolved.is_relative_to(ENV),
                                   'inside_workspace': resolved.is_relative_to(ROOT),
                                   'stub_path': 'stubs' in resolved.parts}
        if query_nvrtc:
            import ctypes
            for row in rows.values():
                if row['kind'] != 'nvrtc':
                    continue
                try:
                    handle = ctypes.CDLL(row['resolved_path'], mode=os.RTLD_NOLOAD | os.RTLD_LOCAL)
                    function = handle.nvrtcVersion
                    function.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
                    function.restype = ctypes.c_int
                    major, minor = ctypes.c_int(), ctypes.c_int()
                    code = function(ctypes.byref(major), ctypes.byref(minor))
                    row['nvrtc_version_query'] = {'exit_code': code, 'major': major.value, 'minor': minor.value,
                                                  'already_loaded_handle_only': True}
                except Exception as error:
                    row['nvrtc_version_query_error'] = type(error).__name__
        return {'files': sorted(rows.values(), key=lambda row: row['resolved_path'])}
    except Exception as error:
        return {'files': sorted(rows.values(), key=lambda row: row['resolved_path']),
                'maps_read_error': type(error).__name__}


def check_runtime_paths(mapped):
    require('maps_read_error' not in mapped, 'Cannot inspect loaded CUDA libraries.')
    for row in mapped['files']:
        require(not row['stub_path'], 'CUDA stub library was loaded.')
        if row['kind'] != 'driver':
            require(row['inside_python_environment'], 'Unexpected external CUDA/package library: ' + row['path'])
    require(any(row['kind'] == 'driver' for row in mapped['files']), 'Real driver mapping was not found.')
    # Pinned wheels intentionally bundle cudart12.6/NVRTC12.6. Their presence is
    # recorded, not mislabeled as system12.2 pollution or silently replaced.


def check_boundary(gpu_uuid):
    require(sys.flags.isolated and sys.flags.no_site and not sys.flags.optimize, 'Use Python -I -B -S without -O.')
    require(Path(sys.prefix).resolve() == ENV, 'Wrong Python environment.')
    require(ROOT.resolve() == ROOT and SITE.resolve().is_relative_to(ENV), 'Unsafe workspace/site path.')
    require(os.environ.get('PHYSX_ROOT') == str(ROOT), 'Use the reviewed isolated launcher.')
    require(re.fullmatch(r'GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', gpu_uuid), 'Full GPU UUID required.')
    require(os.environ.get('CUDA_VISIBLE_DEVICES', '').lower() == gpu_uuid.lower(), 'Selected UUID differs from CUDA visibility.')
    for path in ['/usr/local', '/etc', '/home/minsujo', str(ENV), str(ROOT / 'toolchains/cuda-12.8.1')]:
        require(os.statvfs(path).f_flag & os.ST_RDONLY, 'Expected read-only mount missing: ' + path)
    require(not os.statvfs(ROOT).f_flag & os.ST_RDONLY, 'Workspace output must be writable.')
    nodes = [p.name for p in Path('/dev').iterdir() if re.fullmatch(r'nvidia\d+', p.name)]
    require(len(nodes) == 1, 'Exactly one selected GPU device node must be exposed.')
    for key in ['TMPDIR', 'CUDA_CACHE_PATH', 'TORCH_HOME', 'TORCH_EXTENSIONS_DIR']:
        require(key in os.environ and Path(os.environ[key]).resolve().is_relative_to(ROOT), 'Unscoped temporary/cache path: ' + key)
    for key in ['LD_PRELOAD', 'LD_AUDIT', 'PYTHONPATH', 'PYTHONHOME', 'SSH_AUTH_SOCK', 'GH_TOKEN', 'GITHUB_TOKEN', 'HF_TOKEN']:
        require(key not in os.environ, 'Unexpected inherited loader or credential variable.')
    # These disable editable-package extension builds, not driver PTX JIT or
    # NVRTC fallback. The latter may occur in the separately authorized trial.
    os.environ['CUMM_DISABLE_JIT'] = '1'
    os.environ['SPCONV_DISABLE_JIT'] = '1'
    versions = {d.metadata['Name'].lower().replace('_', '-'): d.version
                for d in importlib.metadata.distributions(path=[str(SITE)])}
    require(all(versions.get(name) == version for name, version in EXPECTED.items()), 'Pinned package metadata differs.')
    return {name: versions[name] for name in EXPECTED}


def execute(gpu_uuid, result_directory=None):
    global RESULT, TRACEBACK
    directory = Path(result_directory) if result_directory else RUN / ('sparse-check-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:10])
    require(directory.is_absolute() and directory.resolve() == directory and directory.is_relative_to(RUN), 'Result directory must be a canonical child of the task log directory.')
    require(directory.parent.is_dir(), 'Result directory parent must already exist.')
    directory.mkdir(mode=0o700, exist_ok=False)
    RESULT = directory / 'result.json'
    TRACEBACK = directory / 'traceback.log'
    require(not RESULT.exists() and not RESULT.is_symlink(), 'Existing result must be preserved; do not replay silently.')
    require(not TRACEBACK.exists() and not TRACEBACK.is_symlink(), 'Existing traceback must be preserved.')
    state = {'started': utc(), 'selected_gpu_uuid': gpu_uuid, 'phase': 'preflight', 'status': 'running',
             'cases': [], 'coordinate_order': 'batch,z,y,x', 'spatial_shape': [5, 5, 5],
             'features_shape': [8, 4], 'weight_shape': [4, 3, 3, 3, 4],
             'atol': 1e-5, 'rtol': 1e-4,
             'limit': 'Two tiny forward cases only; no backward, FP16, model, installation, or source build. Internal autotuning/PTX JIT/NVRTC may execute multiple kernels.'}
    try:
        state['installed_versions'] = check_boundary(gpu_uuid)
        state['phase'] = 'importing_torch_and_sparse_packages'
        save(state)
        sys.path.insert(0, str(SITE))
        import torch
        import torchvision
        import spconv
        import spconv.pytorch as sparse
        import spconv.constants as sparse_constants
        import cumm
        from spconv.core import ConvAlgo
        require(torch.__version__ == EXPECTED['torch'] and torchvision.__version__ == EXPECTED['torchvision'], 'Imported torch versions differ.')
        require(spconv.__version__ == '2.3.8' and cumm.__version__ == '0.7.11', 'Imported sparse versions differ.')
        require(torch.version.cuda == '12.8', 'Unexpected torch CUDA build.')
        require(torch.cuda.is_available() and torch.cuda.device_count() == 1, 'Exactly one logical CUDA device is required.')
        properties = torch.cuda.get_device_properties(0)
        require((properties.major, properties.minor) == (12, 0), 'Expected selected SM120 device.')
        actual_uuid = getattr(properties, 'uuid', None)
        require(actual_uuid is not None and str(actual_uuid).lower().removeprefix('gpu-') == gpu_uuid.lower().removeprefix('gpu-'), 'Torch device UUID differs or is unavailable.')
        state['device'] = {'name': properties.name, 'uuid': str(actual_uuid), 'capability': [properties.major, properties.minor], 'logical_index': 0}
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        sparse_constants.SPCONV_ALLOW_TF32 = False
        torch.set_grad_enabled(False)
        torch.set_num_threads(1)
        initial_maps = mapped_libraries(query_nvrtc=True)
        check_runtime_paths(initial_maps)
        state['libraries_after_import'] = initial_maps
        state['phase'] = 'cpu_reference'
        save(state)
        features = ((torch.arange(32, dtype=torch.float32).reshape(8, 4) % 17) - 8) / 16
        weights = ((torch.arange(432, dtype=torch.float32).reshape(4, 3, 3, 3, 4) % 13) - 6) / 64
        dense = torch.zeros((1, 4, 5, 5, 5), dtype=torch.float64, device='cpu')
        for index, (batch, z, y, x) in enumerate(COORDINATES):
            dense[batch, :, z, y, x] = features[index].to(torch.float64)
        reference_dense = torch.nn.functional.conv3d(dense, weights.permute(0, 4, 1, 2, 3).contiguous().to(torch.float64), padding=1)
        ordered_coords = sorted(map(tuple, COORDINATES))
        reference = torch.stack([reference_dense[b, :, z, y, x] for b, z, y, x in ordered_coords])
        for name, algorithm in [('native', ConvAlgo.Native), ('auto', None)]:
            case = {'case': name, 'started': utc(), 'status': 'running'}
            state['cases'].append(case)
            state['phase'] = 'case_' + name
            save(state)
            started = time.monotonic()
            torch.cuda.reset_peak_memory_stats(0)
            layer = sparse.SubMConv3d(4, 4, kernel_size=3, padding=1, bias=False, algo=algorithm)
            require(list(layer.weight.shape) == [4, 3, 3, 3, 4], 'Unexpected KRSC weight layout.')
            layer.weight.copy_(weights)
            layer = layer.eval().to('cuda:0')
            tensor = sparse.SparseConvTensor(features.to('cuda:0'),
                                            torch.tensor(COORDINATES, dtype=torch.int32, device='cuda:0'),
                                            spatial_shape=[5, 5, 5], batch_size=1)
            with torch.inference_mode():
                output = layer(tensor)
            torch.cuda.synchronize(0)
            coordinates = [tuple(x) for x in output.indices.detach().cpu().tolist()]
            require(len(coordinates) == len(set(coordinates)) == len(ordered_coords), 'Duplicate or missing sparse coordinates.')
            require(sorted(coordinates) == ordered_coords, 'SubM output coordinate set changed.')
            ordering = sorted(range(len(coordinates)), key=coordinates.__getitem__)
            actual = output.features.detach().cpu()[ordering].to(torch.float64)
            require(tuple(actual.shape) == (8, 4) and bool(torch.isfinite(actual).all()), 'Nonfinite or incorrectly shaped sparse output.')
            delta = (actual - reference).abs()
            case.update(actual_algorithm=str(layer.algo), coordinate_set_matches=True,
                        maximum_absolute_error=float(delta.max()),
                        maximum_relative_error=float((delta / reference.abs().clamp_min(1e-12)).max()),
                        peak_torch_allocation_bytes=torch.cuda.max_memory_allocated(0),
                        output_aligned=actual.tolist(), reference_cpu_float64=reference.tolist())
            torch.testing.assert_close(actual, reference, atol=state['atol'], rtol=state['rtol'])
            maps = mapped_libraries(query_nvrtc=True)
            check_runtime_paths(maps)
            case.update(status='passed', finished=utc(), elapsed_seconds=time.monotonic() - started, mapped_libraries=maps)
            save(state)
            del output, tensor, layer
        state.update(status='passed', phase='completed', exit_code=0,
                     claim='Native and automatically selected 3x3 SubMConv forward matched the independent CPU dense reference.')
        return 0
    except BaseException as error:
        state.update(status='failed', exit_code=1, error_type=type(error).__name__, error=str(error))
        if state['cases'] and state['cases'][-1]['status'] == 'running':
            state['cases'][-1].update(status='failed', finished=utc())
        TRACEBACK.write_text(traceback.format_exc())
        traceback.print_exc()
        return 1
    finally:
        state['finished'] = utc()
        state['libraries_finally'] = mapped_libraries(query_nvrtc=True)
        save(state)
        print(json.dumps({'status': state['status'], 'exit_code': state.get('exit_code'), 'result': str(RESULT)}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--gpu-uuid')
    parser.add_argument('--result-dir', help='New task-log child directory; default creates a unique directory per execution.')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'mode': 'plan', 'executed': False, 'cases': ['native', 'auto'],
                          'features_shape': [8, 4], 'subm_kernel': [3, 3, 3],
                          'cpu_reference': 'float64 dense conv3d sampled at aligned active coordinates',
                          'result_directory': args.result_dir or str(RUN / 'sparse-check-<UTC>-<unique>')}, indent=2))
        return 0
    require(args.gpu_uuid is not None, '--execute requires --gpu-uuid.')
    return execute(args.gpu_uuid, args.result_dir)


if __name__ == '__main__':
    raise SystemExit(main())
