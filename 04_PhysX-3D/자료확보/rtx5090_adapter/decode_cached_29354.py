#!/usr/bin/env python3
"""Decode the verified 29354 latent without repeating image sampling."""

import argparse
import gc
import json
import os
from pathlib import Path
import time

import torch


def gpu_snapshot(label):
    data = {
        'label': label,
        'allocated_mib': round(torch.cuda.memory_allocated() / 2**20, 3),
        'reserved_mib': round(torch.cuda.memory_reserved() / 2**20, 3),
        'max_allocated_mib': round(torch.cuda.max_memory_allocated() / 2**20, 3),
    }
    print(json.dumps({'gpu_memory': data}), flush=True)
    return data


def parameter_bytes(model):
    return sum(p.numel() * p.element_size() for p in model.parameters()) + sum(
        b.numel() * b.element_size() for b in model.buffers())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--latent', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()

    source = Path(args.source).resolve()
    output = Path(args.output).resolve()
    report_path = Path(args.report).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {
        'started': time.time(),
        'scope': 'cached latent -> physics decoder -> mesh decoder',
        'spconv_algo_requested': os.environ.get('SPCONV_ALGO'),
        'not_loaded': [
            'image_cond_model', 'sparse_structure_decoder', 'sparse_structure_flow_model',
            'slat_flow_model', 'slat_flow_model_phy', 'slat_decoder_gs',
            'slat_decoder_rf', 'slat_decoder_output', 'CLIP ViT-L/14',
        ],
        'moved_off_gpu': [],
        'memory': [],
    }

    from trellis import models
    from trellis.modules import sparse as sp
    from trellis.modules.sparse import conv as sparse_conv

    report['spconv_algo_actual'] = sparse_conv.SPCONV_ALGO
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'spconv_algo_requested': report['spconv_algo_requested'],
                      'spconv_algo_actual': report['spconv_algo_actual']}), flush=True)
    if report['spconv_algo_requested'] != 'native' or report['spconv_algo_actual'] != 'native':
        report['status'] = 'failed_before_decoder'
        report['reason'] = 'SPCONV_ALGO native selection required'
        report_path.write_text(json.dumps(report, indent=2) + '\n')
        raise RuntimeError('SPCONV_ALGO native selection required before decoder')
    report['status'] = 'running'
    report_path.write_text(json.dumps(report, indent=2) + '\n')

    cache = torch.load(args.latent, map_location='cpu', weights_only=True)
    required = {'slat_coords', 'slat_feats', 'phy_coords', 'phy_feats', 'cpu_rng', 'cuda_rng'}
    if set(cache) != required:
        raise RuntimeError(f'cached latent keys differ: {sorted(cache)}')
    if not torch.equal(cache['slat_coords'], cache['phy_coords']):
        raise RuntimeError('cached geometry/physics coordinates differ')
    for name in ('slat_feats', 'phy_feats'):
        if cache[name].shape != (33886, 8) or cache[name].dtype != torch.float32:
            raise RuntimeError(f'unexpected cached latent: {name}')
        if not torch.isfinite(cache[name]).all():
            raise RuntimeError(f'nonfinite cached latent: {name}')

    torch.cuda.reset_peak_memory_stats()
    report['memory'].append(gpu_snapshot('before_models'))
    phy_model_path = source / 'pretrain/diffusion/ckpts_new/property_decoder_step0100000.pt'
    mesh_model_path = source / 'pretrain/diffusion/ckpts_new/decoder_step0100000.pt'

    physics_decoder = models.from_pretrained_config(str(phy_model_path)).eval()
    report['physics_decoder_parameter_bytes'] = parameter_bytes(physics_decoder)
    physics_decoder.cuda()
    phy_latent = sp.SparseTensor(feats=cache['phy_feats'].cuda(), coords=cache['phy_coords'].cuda())
    report['memory'].append(gpu_snapshot('physics_decoder_loaded'))
    with torch.inference_mode():
        decoded_physics, physics_skip = physics_decoder(phy_latent)
        torch.cuda.synchronize()
    report['memory'].append(gpu_snapshot('physics_decoder_complete'))
    if not torch.isfinite(decoded_physics.feats).all().item():
        raise RuntimeError('nonfinite decoded physics')

    # The mesh decoder needs decoded_physics and physics_skip[0], but not the decoder weights.
    physics_decoder.cpu()
    del physics_decoder, phy_latent, cache['phy_feats']
    gc.collect()
    torch.cuda.empty_cache()
    report['moved_off_gpu'].append('slat_decoder_phy weights')
    report['memory'].append(gpu_snapshot('physics_decoder_weights_released'))

    mesh_decoder = models.from_pretrained_config(str(mesh_model_path)).eval()
    report['mesh_decoder_parameter_bytes'] = parameter_bytes(mesh_decoder)
    mesh_decoder.cuda()
    slat = sp.SparseTensor(feats=cache['slat_feats'].cuda(), coords=cache['slat_coords'].cuda())
    del cache
    gc.collect()
    torch.cuda.empty_cache()
    report['memory'].append(gpu_snapshot('mesh_decoder_loaded'))
    with torch.inference_mode():
        meshes = mesh_decoder(slat, decoded_physics, physics_skip)
        torch.cuda.synchronize()
    report['memory'].append(gpu_snapshot('mesh_decoder_complete'))
    if len(meshes) != 1 or not meshes[0].success:
        raise RuntimeError('mesh decoder did not produce one valid mesh')
    mesh = meshes[0]
    tensors = {
        'vertices': mesh.vertices.detach().cpu(),
        'faces': mesh.faces.detach().cpu(),
        'vertex_attrs': None if mesh.vertex_attrs is None else mesh.vertex_attrs.detach().cpu(),
        'vertex_physics': None if mesh.phy_property is None else mesh.phy_property.detach().cpu(),
    }
    for key, value in tensors.items():
        if value is not None and value.is_floating_point() and not torch.isfinite(value).all():
            raise RuntimeError(f'nonfinite mesh tensor: {key}')
    torch.save(tensors, output / 'mesh_physics_raw.pt')

    import trimesh
    trimesh.Trimesh(vertices=tensors['vertices'].numpy(), faces=tensors['faces'].numpy(),
                    process=False).export(output / 'mesh.obj')
    report['mesh'] = {
        'vertices': len(tensors['vertices']), 'faces': len(tensors['faces']),
        'vertex_attrs_shape': None if tensors['vertex_attrs'] is None else list(tensors['vertex_attrs'].shape),
        'vertex_physics_shape': None if tensors['vertex_physics'] is None else list(tensors['vertex_physics'].shape),
    }
    report['finished'] = time.time()
    report['status'] = 'success'
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'decoder_complete': True, **report['mesh']}), flush=True)


if __name__ == '__main__':
    main()
