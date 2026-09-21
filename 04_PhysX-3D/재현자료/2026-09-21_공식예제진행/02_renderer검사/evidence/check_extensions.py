"""Prepare or explicitly execute one small native extension check.

Default prints a plan with no package import, subprocess, GPU query or write.
--execute is only for the authorized offline workspace_runner GPU profile.
Each execution creates a new result directory. No model or download is used.
Nvdiffrast may compile its CUDA plugin in the workspace extension cache.
"""
import argparse
import datetime
import importlib.metadata
import json
import math
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
TOOLKIT = ROOT / 'toolchains/cuda-12.8.1'
BASE = ROOT / 'logs/official-example-20260921'
PINS = {'kaolin': ('kaolin', '0.18.0'), 'nvdiffrast': ('nvdiffrast', '0.3.3'),
        'gaussian': ('diff-gaussian-rasterization', '0.0.0'), 'flashattn': ('flash-attn', '2.8.3')}
EXPECTED_TORCH = '2.7.1+cu128'
RESULT = None


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def save(state):
    require(RESULT.parent.resolve() == RESULT.parent and RESULT.is_relative_to(BASE), 'Unsafe result path.')
    require(not RESULT.is_symlink(), 'Result may not be a symlink.')
    RESULT.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')


def mappings():
    rows = {}
    try:
        for line in Path('/proc/self/maps').read_text().splitlines():
            fields = line.split(maxsplit=5)
            if len(fields) != 6 or not fields[5].startswith('/'):
                continue
            path = Path(fields[5]).resolve()
            name = path.name
            kind = None
            for prefix, label in [('libnvrtc-builtins', 'nvrtc_builtins'), ('libnvrtc', 'nvrtc'),
                                  ('libcudart', 'cudart'), ('libcuda.so', 'driver'),
                                  ('libtorch_cuda', 'torch_cuda'), ('libcublas', 'cublas')]:
                if name.startswith(prefix):
                    kind = label
                    break
            if '.so' in name and (any(part in path.parts for part in ['kaolin', 'diff_gaussian_rasterization'])
                                 or name.startswith(('flash_attn', 'nvdiffrast'))):
                kind = 'extension'
            if kind:
                rows[str(path)] = {'path': str(path), 'kind': kind,
                                   'inside_workspace': path.is_relative_to(ROOT),
                                   'stub_path': 'stubs' in path.parts}
        import ctypes
        for row in rows.values():
            if row['kind'] == 'nvrtc':
                try:
                    library = ctypes.CDLL(row['path'], mode=os.RTLD_NOLOAD | os.RTLD_LOCAL)
                    function = library.nvrtcVersion
                    function.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
                    function.restype = ctypes.c_int
                    major, minor = ctypes.c_int(), ctypes.c_int()
                    code = function(ctypes.byref(major), ctypes.byref(minor))
                    row['version_query'] = {'exit_code': code, 'major': major.value, 'minor': minor.value,
                                            'already_loaded_handle_only': True}
                except Exception as error:
                    row['version_query_error'] = type(error).__name__
        return {'files': sorted(rows.values(), key=lambda row: row['path'])}
    except Exception as error:
        return {'files': sorted(rows.values(), key=lambda row: row['path']), 'error': type(error).__name__}


def check_mappings(value, expect_extension=False):
    require('error' not in value, 'Could not inspect actual loaded libraries.')
    require(any(row['kind'] == 'driver' for row in value['files']), 'No real driver mapping.')
    for row in value['files']:
        path = Path(row['path'])
        require(not row['stub_path'], 'CUDA stub was loaded.')
        if row['kind'] != 'driver':
            require(any(path.is_relative_to(base) for base in [ENV, TOOLKIT, ROOT / 'build/torch-extensions']),
                    'Unapproved runtime/extension path: ' + row['path'])
    if expect_extension:
        require(any(row['kind'] == 'extension' for row in value['files']), 'Native extension mapping was not observed.')


def boundary(case, gpu_uuid):
    require(sys.flags.isolated and sys.flags.no_site and not sys.flags.optimize, 'Use environment Python -I -B -S without -O.')
    require(Path(sys.prefix).resolve() == ENV and SITE.resolve().is_relative_to(ENV), 'Wrong Python environment.')
    require(os.environ.get('PHYSX_RUN_PROFILE') == 'gpu' and os.environ.get('PHYSX_ROOT') == str(ROOT)
            and os.environ.get('PHYSX_WORKSPACE_ISOLATED') == '1', 'Reviewed GPU profile required.')
    require(re.fullmatch(r'GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', gpu_uuid), 'Full GPU UUID required.')
    require(os.environ.get('CUDA_VISIBLE_DEVICES', '').lower() == gpu_uuid.lower(), 'GPU visibility differs.')
    for path in [Path('/usr/local'), Path('/etc'), Path('/home/minsujo'), ENV, TOOLKIT]:
        require(os.statvfs(path).f_flag & os.ST_RDONLY, 'Expected read-only filesystem missing: ' + str(path))
    require(not (os.statvfs(ROOT).f_flag & os.ST_RDONLY), 'Workspace must be writable.')
    require(len([p for p in Path('/dev').iterdir() if re.fullmatch(r'nvidia\d+', p.name)]) == 1, 'Only one selected GPU node may be exposed.')
    for key in ['TMPDIR', 'CUDA_CACHE_PATH', 'TORCH_HOME', 'TORCH_EXTENSIONS_DIR']:
        require(key in os.environ and Path(os.environ[key]).resolve().is_relative_to(ROOT), 'Unscoped cache/temp path: ' + key)
    for key in ['LD_PRELOAD', 'LD_AUDIT', 'PYTHONPATH', 'PYTHONHOME', 'SSH_AUTH_SOCK', 'GH_TOKEN', 'GITHUB_TOKEN', 'HF_TOKEN']:
        require(key not in os.environ, 'Unexpected inherited loader/credential variable.')
    require(os.environ.get('HF_HUB_OFFLINE') == '1' and os.environ.get('PIP_NO_INDEX') == '1', 'Offline profile expected.')
    distributions = {d.metadata['Name'].lower().replace('_', '-'): d
                     for d in importlib.metadata.distributions(path=[str(SITE)])}
    required = {'torch': EXPECTED_TORCH, 'torchvision': '0.22.1+cu128', PINS[case][0]: PINS[case][1]}
    result = {}
    for name, expected in required.items():
        require(name in distributions and distributions[name].version == expected, 'Package pin differs: ' + name)
        result[name] = {'version': distributions[name].version}
        direct_url = distributions[name].read_text('direct_url.json')
        if direct_url:
            result[name]['direct_url'] = json.loads(direct_url)
    return result


def finite(torch, tensor, label):
    require(bool(torch.isfinite(tensor).all().item()), 'Nonfinite ' + label)


def close(torch, actual, expected, atol=1e-5, rtol=1e-4):
    actual = actual.detach().cpu().to(torch.float64)
    expected = expected.detach().cpu().to(torch.float64)
    finite(torch, actual, 'output')
    torch.testing.assert_close(actual, expected, atol=atol, rtol=rtol)
    return {'shape': list(actual.shape), 'maximum_absolute_error': float((actual - expected).abs().max()),
            'atol': atol, 'rtol': rtol, 'finite': True}


def gradients(torch, tensors):
    results = {}
    for name, tensor in tensors.items():
        require(tensor.grad is not None, 'Missing gradient: ' + name)
        finite(torch, tensor.grad, name + ' gradient')
        results[name] = {'finite': True, 'maximum_absolute_value': float(tensor.grad.detach().abs().max().cpu())}
    return results


def kaolin_case(torch, state):
    import kaolin
    from kaolin.metrics.pointcloud import sided_distance, chamfer_distance
    require(kaolin.__version__ == '0.18.0', 'Imported Kaolin version differs.')
    a = torch.tensor([[[0., 0., 0.], [1., 0., 0.], [0., 2., 0.]]], dtype=torch.float64, requires_grad=True)
    b = torch.tensor([[[0.125, 0., 0.], [1.5, 0., 0.], [0., 2.25, 0.], [2., 3., 1.]]], dtype=torch.float64, requires_grad=True)
    squared = (a[:, :, None, :] - b[:, None, :, :]).square().sum(-1)
    ref_dist, ref_index = squared.min(-1)
    ref_chamfer = ref_dist.mean(-1) + squared.min(-2).values.mean(-1)
    ga = a.detach().to(device='cuda:0', dtype=torch.float32).requires_grad_()
    gb = b.detach().to(device='cuda:0', dtype=torch.float32).requires_grad_()
    distance, index = sided_distance(ga, gb)
    chamfer = chamfer_distance(ga, gb, squared=True)
    torch.cuda.synchronize(0)
    torch.testing.assert_close(index.detach().cpu().to(torch.int64), ref_index.detach())
    report = {'sided_distance': close(torch, distance, ref_dist), 'nearest_indices_match': True,
              'chamfer': close(torch, chamfer, ref_chamfer), 'point_counts': [3, 4]}
    chamfer.sum().backward()
    ref_chamfer.sum().backward()
    torch.cuda.synchronize(0)
    report['gradients'] = gradients(torch, {'points_a': ga, 'points_b': gb})
    report['gradient_reference'] = {'points_a': close(torch, ga.grad, a.grad), 'points_b': close(torch, gb.grad, b.grad)}
    state['checks'] = report


def nvdiffrast_case(torch, state):
    import nvdiffrast.torch as dr
    state['phase'] = 'nvdiffrast_cuda_plugin_load_or_workspace_build'
    save(state)
    context = dr.RasterizeCudaContext(device=0)
    vertices = torch.tensor([[[-0.75, -0.75, 0., 1.], [0.75, -0.75, 0., 1.], [0., 0.75, 0., 1.]]],
                            dtype=torch.float32, device='cuda:0', requires_grad=True)
    triangle = torch.tensor([[0, 1, 2]], dtype=torch.int32, device='cuda:0')
    attributes = torch.eye(3, dtype=torch.float32, device='cuda:0').unsqueeze(0).requires_grad_()
    raster, raster_db = dr.rasterize(context, vertices, triangle, resolution=[16, 16])
    image, derivative = dr.interpolate(attributes, raster, triangle, rast_db=raster_db, diff_attrs='all')
    torch.cuda.synchronize(0)
    require(tuple(image.shape) == (1, 16, 16, 3), 'Unexpected interpolated image shape.')
    finite(torch, raster, 'raster'); finite(torch, raster_db, 'raster derivatives')
    finite(torch, image, 'interpolated image'); finite(torch, derivative, 'attribute derivatives')
    mask = raster.detach().cpu()[0, :, :, 3] > 0
    covered = int(mask.sum())
    require(0 < covered < 256, 'Expected partial triangle coverage.')
    axis = (torch.arange(16, dtype=torch.float64) + 0.5) * (2. / 16) - 1.
    yy, xx = torch.meshgrid(axis, axis, indexing='ij')
    # CPU barycentrics at pixel centers for the fixed clip-space triangle, w=1.
    third = (yy + 0.75) / 1.5
    second = ((xx + 0.75) - 0.75 * third) / 1.5
    first = 1. - second - third
    reference = torch.stack([first, second, third], dim=-1)
    comparison = close(torch, image[0].detach().cpu()[mask], reference[mask], atol=2e-5, rtol=2e-5)
    loss = (image.square() * torch.tensor([1., 2., 3.], device='cuda:0')).mean()
    loss.backward()
    torch.cuda.synchronize(0)
    grads = gradients(torch, {'clip_vertices': vertices, 'vertex_attributes': attributes})
    require(all(row['maximum_absolute_value'] > 0 for row in grads.values()), 'Expected nonzero raster/interpolation gradients.')
    state['checks'] = {'resolution': [16, 16], 'triangles': 1, 'covered_pixels': covered,
                       'cpu_barycentric_reference': comparison, 'gradients': grads, 'cuda_context': True}


def gaussian_case(torch, state):
    from diff_gaussian_rasterization import GaussianRasterizationSettings, GaussianRasterizer
    # Same transpose convention as fixed mip-splatting graphics_utils/cameras.
    projection = torch.zeros((4, 4), dtype=torch.float32)
    near, far = 0.1, 10.
    projection[0, 0] = projection[1, 1] = 1.
    projection[2, 2] = far / (far - near)
    projection[2, 3] = -(far * near) / (far - near)
    projection[3, 2] = 1.
    settings = GaussianRasterizationSettings(
        image_height=16, image_width=16, tanfovx=1., tanfovy=1., kernel_size=0.1,
        subpixel_offset=torch.zeros((16, 16, 2), device='cuda:0'),
        bg=torch.zeros(3, device='cuda:0'), scale_modifier=1.,
        viewmatrix=torch.eye(4, device='cuda:0'), projmatrix=projection.T.contiguous().to('cuda:0'),
        sh_degree=0, campos=torch.zeros(3, device='cuda:0'), prefiltered=False, debug=False)
    means = torch.tensor([[0., 0., 2.]], device='cuda:0', requires_grad=True)
    screenspace = torch.zeros((1, 3), device='cuda:0', requires_grad=True)
    colors = torch.tensor([[0.75, 0.3, 0.1]], device='cuda:0', requires_grad=True)
    opacity = torch.tensor([[0.8]], device='cuda:0', requires_grad=True)
    scales = torch.tensor([[0.15, 0.15, 0.15]], device='cuda:0', requires_grad=True)
    rotations = torch.tensor([[1., 0., 0., 0.]], device='cuda:0', requires_grad=True)
    image, radii = GaussianRasterizer(settings)(means3D=means, means2D=screenspace, opacities=opacity,
                                               colors_precomp=colors, scales=scales, rotations=rotations)
    torch.cuda.synchronize(0)
    require(tuple(image.shape) == (3, 16, 16) and tuple(radii.shape) == (1,), 'Unexpected Gaussian output shape.')
    finite(torch, image, 'Gaussian image')
    require(int(radii[0].cpu()) > 0, 'Gaussian was culled or had zero radius.')
    covered = int((image.detach().sum(0) > 0).sum().cpu())
    require(0 < covered < 256 and float(image.min().detach().cpu()) >= -1e-6, 'Invalid Gaussian coverage/color.')
    require(float(image.max().detach().cpu()) <= 0.75 + 1e-5, 'Single Gaussian exceeded its source color.')
    normalized = image.detach().cpu() / colors.detach().cpu().reshape(3, 1, 1)
    channel_agreement = close(torch, normalized[1:], normalized[:1].expand(2, -1, -1), atol=2e-5, rtol=2e-5)
    (image.sum() / 256).backward()
    torch.cuda.synchronize(0)
    grads = gradients(torch, {'means3D': means, 'means2D': screenspace, 'colors': colors,
                              'opacity': opacity, 'scales': scales, 'rotations': rotations})
    require(grads['colors']['maximum_absolute_value'] > 0 and grads['opacity']['maximum_absolute_value'] > 0,
            'Expected nonzero Gaussian color/opacity gradients.')
    state['checks'] = {'gaussians': 1, 'resolution': [16, 16], 'near_far': [near, far],
                       'camera_forward_positive_z': True, 'radius_pixels': int(radii[0].cpu()),
                       'covered_pixels': covered, 'channel_alpha_agreement': channel_agreement, 'gradients': grads,
                       'scope': 'Finite coverage, single-color alpha agreement and backward; no full CPU rasterizer equivalence claim.'}


def attention_reference(torch, q, k, v):
    q, k, v = [x.detach().cpu().to(torch.float64) for x in (q, k, v)]
    scores = torch.einsum('bshd,bthd->bhst', q, k) / math.sqrt(q.shape[-1])
    return torch.einsum('bhst,bthd->bshd', scores.softmax(dim=-1), v)


def flashattn_case(torch, state):
    import flash_attn
    require(flash_attn.__version__ == '2.8.3', 'Imported FlashAttention version differs.')
    names = ['flash_attn_func', 'flash_attn_kvpacked_func', 'flash_attn_qkvpacked_func',
             'flash_attn_varlen_func', 'flash_attn_varlen_kvpacked_func', 'flash_attn_varlen_qkvpacked_func']
    require(all(callable(getattr(flash_attn, name, None)) for name in names), 'Required FlashAttention API missing.')
    state['subcases'] = []
    lengths = [5, 8]
    cumulative = torch.tensor([0, 5, 13], dtype=torch.int32, device='cuda:0')
    for dtype_name, dtype, atol, rtol in [('fp16', torch.float16, 2e-3, 2e-3), ('bf16', torch.bfloat16, 2e-2, 2e-2)]:
        source = torch.arange(2 * 8 * 2 * 64, dtype=torch.float32).reshape(2, 8, 2, 64)
        cpu = [((source + shift) % divisor - offset) / 16 for shift, divisor, offset in [(0, 17, 8), (3, 19, 9), (5, 23, 11)]]
        q, k, v = [tensor.to(device='cuda:0', dtype=dtype) for tensor in cpu]
        dense_reference = attention_reference(torch, q, k, v)
        qv, kv, vv = [torch.cat([tensor[i, :length] for i, length in enumerate(lengths)], dim=0).contiguous()
                      for tensor in [q, k, v]]
        varlen_reference = torch.cat([attention_reference(torch, q[i:i+1, :length], k[i:i+1, :length], v[i:i+1, :length])[0]
                                      for i, length in enumerate(lengths)], dim=0)
        arguments = {
            names[0]: (q, k, v), names[1]: (q, torch.stack([k, v], dim=2)),
            names[2]: (torch.stack([q, k, v], dim=2),),
            names[3]: (qv, kv, vv, cumulative, cumulative, 8, 8),
            names[4]: (qv, torch.stack([kv, vv], dim=1), cumulative, cumulative, 8, 8),
            names[5]: (torch.stack([qv, kv, vv], dim=1), cumulative, 8),
        }
        for name in names:
            row = {'api': name, 'dtype': dtype_name, 'status': 'running', 'started': utc()}
            state['subcases'].append(row)
            state['phase'] = dtype_name + '_' + name
            save(state)
            began = time.monotonic()
            with torch.no_grad():
                output = getattr(flash_attn, name)(*arguments[name], dropout_p=0., softmax_scale=None, causal=False)
            torch.cuda.synchronize(0)
            reference = varlen_reference if 'varlen' in name else dense_reference
            row.update(close(torch, output, reference, atol=atol, rtol=rtol))
            row.update(status='passed', finished=utc(), elapsed_seconds=time.monotonic() - began)
            save(state)
    state['checks'] = {'api_count': 6, 'dtype_count': 2, 'forward_count': 12, 'dense_shape': [2, 8, 2, 64],
                       'varlen_lengths': lengths, 'dropout': 0., 'causal': False,
                       'reference': 'CPU float64 softmax(QK^T/sqrt(head_dim))V from quantized inputs',
                       'scope': 'Forward only; no backward, long context, causal, GQA, KV-cache or full-model equivalence claim.'}


def execute(args):
    global RESULT
    directory = Path(args.result_dir) if args.result_dir else BASE / ('extension-' + args.case + '-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:10])
    require(directory.is_absolute() and directory.resolve() == directory and directory.is_relative_to(BASE), 'Result directory must be a canonical task-log child.')
    require(directory.parent.is_dir(), 'Result directory parent must exist.')
    directory.mkdir(mode=0o700, exist_ok=False)
    RESULT = directory / 'result.json'
    state = {'case': args.case, 'status': 'running', 'phase': 'preflight', 'started': utc(),
             'selected_gpu_uuid': args.gpu_uuid, 'script': str(Path(__file__).resolve()),
             'limit': 'One selected bounded extension case, offline; no model, downloads or installation.'}
    began = time.monotonic()
    torch = None
    try:
        state['packages'] = boundary(args.case, args.gpu_uuid)
        state['phase'] = 'torch_import'
        save(state)
        sys.path.insert(0, str(SITE))
        import torch as imported_torch
        torch = imported_torch
        require(torch.__version__ == EXPECTED_TORCH and torch.version.cuda == '12.8', 'Imported torch/CUDA version differs.')
        require(torch.cuda.is_available() and torch.cuda.device_count() == 1, 'Exactly one logical CUDA device required.')
        properties = torch.cuda.get_device_properties(0)
        actual_uuid = getattr(properties, 'uuid', None)
        require(actual_uuid is not None and str(actual_uuid).lower().removeprefix('gpu-') == args.gpu_uuid.lower().removeprefix('gpu-'), 'Selected UUID differs or is unavailable.')
        require((properties.major, properties.minor) == (12, 0), 'Expected SM120 device.')
        state['device'] = {'uuid': str(actual_uuid), 'name': properties.name, 'capability': [properties.major, properties.minor], 'logical_index': 0}
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.set_num_threads(1)
        torch.cuda.reset_peak_memory_stats(0)
        state['libraries_before'] = mappings()
        check_mappings(state['libraries_before'])
        state['phase'] = args.case
        save(state)
        {'kaolin': kaolin_case, 'nvdiffrast': nvdiffrast_case, 'gaussian': gaussian_case, 'flashattn': flashattn_case}[args.case](torch, state)
        state['libraries_after'] = mappings()
        check_mappings(state['libraries_after'], expect_extension=True)
        state.update(status='passed', exit_code=0, phase='completed')
        return 0
    except BaseException as error:
        state.update(status='failed', exit_code=1, error_type=type(error).__name__, error=str(error))
        if state.get('subcases') and state['subcases'][-1]['status'] == 'running':
            state['subcases'][-1].update(status='failed', finished=utc())
        (directory / 'traceback.log').write_text(traceback.format_exc())
        traceback.print_exc()
        return 1
    finally:
        state.update(finished=utc(), elapsed_seconds=time.monotonic() - began, libraries_finally=mappings())
        if torch is not None and 'device' in state:
            try:
                state['peak_torch_allocation_bytes'] = torch.cuda.max_memory_allocated(0)
                state['peak_torch_reserved_bytes'] = torch.cuda.max_memory_reserved(0)
            except Exception as error:
                state['allocation_query_error'] = type(error).__name__
        save(state)
        print(json.dumps({'case': args.case, 'status': state['status'], 'exit_code': state.get('exit_code'), 'result': str(RESULT)}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True, choices=sorted(PINS))
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--gpu-uuid')
    parser.add_argument('--result-dir')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'mode': 'plan', 'executed': False, 'case': args.case, 'package_pin': PINS[args.case],
                          'torch_pin': EXPECTED_TORCH, 'gpu_required_for_execute': 'Exactly one selected SM120 UUID',
                          'result_directory': args.result_dir or str(BASE / ('extension-' + args.case + '-<UTC>-<unique>'))}, indent=2))
        return 0
    require(args.gpu_uuid is not None, '--execute requires --gpu-uuid.')
    return execute(args)


if __name__ == '__main__':
    raise SystemExit(main())
