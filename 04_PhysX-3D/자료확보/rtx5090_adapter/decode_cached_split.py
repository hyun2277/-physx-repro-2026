#!/usr/bin/env python3
"""Run one half of cached PhysX-3D decoding in an isolated GPU process."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import torch


def sparse_pack(x):
    return {"feats": x.feats.detach().cpu(), "coords": x.coords.detach().cpu(),
            "shape": list(x.shape), "scale": list(x._scale)}


def sparse_unpack(sp, value, device="cuda"):
    x = sp.SparseTensor(feats=value["feats"].to(device), coords=value["coords"].to(device),
                        shape=torch.Size(value["shape"]))
    x._scale = tuple(value["scale"])
    return x


def validate_latent(cache):
    required = {"slat_coords", "slat_feats", "phy_coords", "phy_feats", "cpu_rng", "cuda_rng"}
    if set(cache) != required or not torch.equal(cache["slat_coords"], cache["phy_coords"]):
        raise RuntimeError("cached latent schema/coordinate mismatch")
    for key in ("slat_feats", "phy_feats"):
        if cache[key].ndim != 2 or cache[key].shape[1] != 8 or cache[key].dtype != torch.float32 or not torch.isfinite(cache[key]).all():
            raise RuntimeError(f"invalid cached latent {key}")
    return int(len(cache["slat_coords"]))


def install_adapters():
    from trellis.modules.sparse import conv
    import output_channel_tiled_spconv as output_adapter
    import memory_bounded_groupnorm as groupnorm_adapter
    requested = os.environ.get("SPCONV_ALGO")
    if requested != "native" or conv.SPCONV_ALGO != "native":
        raise RuntimeError(f"native spconv required: requested={requested}, actual={conv.SPCONV_ALGO}")
    if os.environ.get("PHYSX_OUTPUT_TILE_ENABLE") != "1" or os.environ.get("PHYSX_STREAMING_GROUPNORM_ENABLE") != "1":
        raise RuntimeError("validated output tiling and streaming GroupNorm must be enabled")
    output_adapter.install(); groupnorm_adapter.install()
    return {"requested": requested, "actual": conv.SPCONV_ALGO}


def physics(args, report):
    from trellis import models
    from trellis.modules import sparse as sp
    cache = torch.load(args.latent, map_location="cpu", weights_only=True)
    report["latent_rows"] = validate_latent(cache)
    model = models.from_pretrained_config(str(Path(args.source) / "pretrain/diffusion/ckpts_new/property_decoder_step0100000.pt")).eval().cuda()
    latent = sp.SparseTensor(feats=cache["phy_feats"].cuda(), coords=cache["phy_coords"].cuda())
    with torch.inference_mode():
        decoded, skips = model(latent); torch.cuda.synchronize()
    packed = {"decoded_physics": sparse_pack(decoded), "physics_skip": [sparse_pack(x) for x in skips]}
    for value in [packed["decoded_physics"], *packed["physics_skip"]]:
        if not torch.isfinite(value["feats"]).all(): raise RuntimeError("non-finite physics intermediate")
    torch.save(packed, args.output)
    report["output"] = {"decoded_shape": list(decoded.feats.shape), "skip_shapes": [list(x.feats.shape) for x in skips]}


def mesh(args, report):
    from trellis import models
    from trellis.modules import sparse as sp
    cache = torch.load(args.latent, map_location="cpu", weights_only=True)
    report["latent_rows"] = validate_latent(cache)
    intermediate = torch.load(args.physics_cache, map_location="cpu", weights_only=True)
    decoded = sparse_unpack(sp, intermediate["decoded_physics"])
    skips = [sparse_unpack(sp, x) for x in intermediate["physics_skip"]]
    model = models.from_pretrained_config(str(Path(args.source) / "pretrain/diffusion/ckpts_new/decoder_step0100000.pt")).eval().cuda()
    slat = sp.SparseTensor(feats=cache["slat_feats"].cuda(), coords=cache["slat_coords"].cuda())
    with torch.inference_mode():
        meshes = model(slat, decoded, skips); torch.cuda.synchronize()
    if len(meshes) != 1 or not meshes[0].success: raise RuntimeError("mesh decoder produced no valid mesh")
    mesh = meshes[0]
    tensors = {"vertices": mesh.vertices.detach().cpu(), "faces": mesh.faces.detach().cpu(),
               "vertex_attrs": None if mesh.vertex_attrs is None else mesh.vertex_attrs.detach().cpu(),
               "vertex_physics": None if mesh.phy_property is None else mesh.phy_property.detach().cpu()}
    for key, value in tensors.items():
        if value is not None and value.is_floating_point() and not torch.isfinite(value).all(): raise RuntimeError(f"non-finite {key}")
    args.output.mkdir(parents=True, exist_ok=False); torch.save(tensors, args.output / "mesh_physics_raw.pt")
    import trimesh
    trimesh.Trimesh(vertices=tensors["vertices"].numpy(), faces=tensors["faces"].numpy(), process=False).export(args.output / "mesh.obj")
    report["output"] = {"vertices": len(tensors["vertices"]), "faces": len(tensors["faces"]),
                        "vertex_physics_shape": list(tensors["vertex_physics"].shape)}


def main():
    p = argparse.ArgumentParser(); p.add_argument("mode", choices=("physics", "mesh")); p.add_argument("--latent", type=Path, required=True)
    p.add_argument("--source", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    p.add_argument("--physics-cache", type=Path); p.add_argument("--report", type=Path, required=True); a = p.parse_args()
    if a.mode == "mesh" and not a.physics_cache: raise SystemExit("mesh mode requires --physics-cache")
    report = {"status": "running", "mode": a.mode, "started": time.time()}
    try:
        report["spconv_algo"] = install_adapters(); torch.cuda.reset_peak_memory_stats()
        globals()[a.mode](a, report)
        report["torch_peak_allocated_mib"] = round(torch.cuda.max_memory_allocated() / 2**20, 3)
        report.update(status="success", finished=time.time())
    except BaseException as exc:
        report.update(status="failed", reason=f"{type(exc).__name__}: {exc}", finished=time.time())
        a.report.write_text(json.dumps(report, indent=2) + "\n"); raise
    a.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__": main()
