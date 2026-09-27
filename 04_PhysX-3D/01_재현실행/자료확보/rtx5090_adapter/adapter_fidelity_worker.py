#!/usr/bin/env python3
"""Numerical probes for the isolated RTX 5090 sparse runtime adapters.

This file never samples an image-conditioned model.  It uses a saved 29354
latent only to retain its sparse-coordinate distribution and it reads decoder
checkpoints without modifying them.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import torch


def metrics(reference: torch.Tensor, candidate: torch.Tensor) -> dict:
    if reference.shape != candidate.shape:
        raise RuntimeError(f"shape mismatch: {tuple(reference.shape)} vs {tuple(candidate.shape)}")
    if not torch.isfinite(reference).all() or not torch.isfinite(candidate).all():
        raise RuntimeError("non-finite comparison input")
    ref = reference.float()
    got = candidate.float()
    delta = got - ref
    denom = torch.linalg.vector_norm(ref).clamp_min(torch.finfo(torch.float32).tiny)
    cosine = torch.nn.functional.cosine_similarity(ref.reshape(1, -1), got.reshape(1, -1)).item()
    return {
        "shape": list(reference.shape),
        "dtype": str(reference.dtype),
        "finite": True,
        "max_abs_error": float(delta.abs().max()),
        "mean_abs_error": float(delta.abs().mean()),
        "relative_l2_error": float(torch.linalg.vector_norm(delta) / denom),
        "cosine_similarity": float(cosine),
        "reference_max_abs": float(ref.abs().max()),
    }


def tolerance(dtype: torch.dtype, repeat: dict) -> dict:
    # Four ULP-scale margins on top of the observed same-kernel repeat error.
    eps = torch.finfo(dtype).eps
    absolute = max(4.0 * repeat["max_abs_error"], 16.0 * eps * repeat["reference_max_abs"])
    relative_l2 = max(4.0 * repeat["relative_l2_error"], 16.0 * eps)
    return {"basis": "max(4x original-repeat error, 16x dtype epsilon scaled by output magnitude)",
            "max_abs_error": float(absolute), "relative_l2_error": float(relative_l2),
            "min_cosine_similarity": float(1.0 - max(4.0 * (1.0 - repeat["cosine_similarity"]), 32.0 * eps))}


def judged(delta: dict, limits: dict) -> bool:
    return (delta["finite"] and delta["max_abs_error"] <= limits["max_abs_error"]
            and delta["relative_l2_error"] <= limits["relative_l2_error"]
            and delta["cosine_similarity"] >= limits["min_cosine_similarity"])


def source_coordinates(cache: dict, repeats: int = 4) -> tuple[torch.Tensor, torch.Tensor]:
    coords = cache["phy_coords"].cpu()
    features = cache["phy_feats"].cpu()
    # Four disjoint copies retain the actual local coordinate pattern and batch
    # ordering while making a practical 135,544-row comparison case.
    copies = []
    values = []
    x_span = int(coords[:, 1].max()) + 1
    for index in range(repeats):
        c = coords.clone()
        c[:, 1] += index * (x_span + 1)
        copies.append(c)
        values.append(features)
    return torch.cat(copies), torch.cat(values)


def find_checkpoint_modules(source: Path):
    from trellis import models
    import spconv.pytorch as spconv
    from trellis.modules.sparse.norm import SparseGroupNorm32

    model = models.from_pretrained_config(str(source / "pretrain/diffusion/ckpts_new/property_decoder_step0100000.pt")).eval()
    convs = [(name, module) for name, module in model.named_modules()
             if isinstance(module, spconv.SubMConv3d)]
    norms = [(name, module) for name, module in model.named_modules()
             if isinstance(module, SparseGroupNorm32)]
    preferred = [(name, m) for name, m in convs if m.in_channels == 512 and m.out_channels == 256]
    if not preferred:
        raise RuntimeError("checkpoint has no 512->256 Native SubMConv3d for production-width probe")
    norm_preferred = [(name, m) for name, m in norms if m.num_channels == 256 and m.num_groups == 32 and m.affine]
    if not norm_preferred:
        raise RuntimeError("checkpoint has no affine SparseGroupNorm32(32, 256) for production-width probe")
    return model, preferred[0], norm_preferred[0]


def make_sparse(coords: torch.Tensor, features: torch.Tensor):
    import spconv.pytorch as spconv
    spatial = (coords[:, 1:].max(dim=0).values + 1).tolist()
    return spconv.SparseConvTensor(features, coords, spatial, int(coords[:, 0].max()) + 1)


def run_conv_probes(source: Path, latent: Path) -> dict:
    import spconv.pytorch as spconv
    import channel_tiled_spconv as channel
    import output_channel_tiled_spconv as output

    cache = torch.load(latent, map_location="cpu", weights_only=True)
    coords_cpu, actual_feats = source_coordinates(cache)
    model, (name, original), _ = find_checkpoint_modules(source)
    if original.algo != spconv.ConvAlgo.Native:
        raise RuntimeError("checkpoint target is not Native spconv")
    # The channel width, kernel, output width and actual checkpoint kernel are
    # retained.  The input repeats the saved 8-channel latent to 512 channels.
    if original.in_channels % actual_feats.shape[1]:
        raise RuntimeError("cannot derive production-width features from saved latent")
    features_cpu = actual_feats.repeat(1, original.in_channels // actual_feats.shape[1]).half()
    coords = coords_cpu.cuda(non_blocking=False)
    sparse = make_sparse(coords, features_cpu.cuda(non_blocking=False))
    conv = original.cuda().half().eval()
    target = {"module": name, "weight_shape": list(conv.weight.shape), "checkpoint_weight_dtype": str(original.weight.dtype), "bias": conv.bias is not None,
              "N": len(coords), "C": conv.in_channels, "O": conv.out_channels,
              "kernel": list(conv.kernel_size), "dtype": "torch.float16",
              "coordinates": {"source": "four disjoint copies of saved 29354 phy_coords", "batch_count": 1,
                              "source_rows": int(len(cache["phy_coords"]))}}
    with torch.inference_mode():
        first = channel.ORIGINAL_FORWARD(conv, sparse)
        second = channel.ORIGINAL_FORWARD(conv, sparse)
        torch.cuda.synchronize()
        repeat = metrics(first.features, second.features)
        limits = tolerance(torch.float16, repeat)

        os.environ["PHYSX_TILE_TEST_FORCE"] = "1"
        os.environ["PHYSX_TILE_TEST_CHANNELS"] = "256"
        try:
            channel_actual = channel._tiled_forward(conv, sparse)
        finally:
            os.environ.pop("PHYSX_TILE_TEST_FORCE", None)
            os.environ.pop("PHYSX_TILE_TEST_CHANNELS", None)
        torch.cuda.synchronize()
        channel_delta = metrics(first.features, channel_actual.features)

        os.environ["PHYSX_OUTPUT_TILE_TEST_FORCE"] = "1"
        os.environ["PHYSX_OUTPUT_TILE_TEST_INPUT_CHANNELS"] = "256"
        os.environ["PHYSX_OUTPUT_TILE_TEST_OUTPUT_CHANNELS"] = "96"
        try:
            output_actual = output._output_tiled_forward(conv, sparse)
        finally:
            for key in ("PHYSX_OUTPUT_TILE_TEST_FORCE", "PHYSX_OUTPUT_TILE_TEST_INPUT_CHANNELS",
                        "PHYSX_OUTPUT_TILE_TEST_OUTPUT_CHANNELS"):
                os.environ.pop(key, None)
        torch.cuda.synchronize()
        output_delta = metrics(first.features, output_actual.features)
    if not torch.equal(first.indices, channel_actual.indices) or not torch.equal(first.indices, output_actual.indices):
        raise RuntimeError("adapter changed sparse coordinate order")
    report = {"target": target, "original_repeat": repeat, "tolerance": limits,
              "channel_tiled": {"metrics": channel_delta, "pass": judged(channel_delta, limits)},
              "output_channel_tiled": {"metrics": output_delta, "pass": judged(output_delta, limits)},
              "same_coordinates": True}
    del channel_actual, output_actual, first, second, sparse, coords, conv, model
    torch.cuda.empty_cache()
    if not report["channel_tiled"]["pass"] or not report["output_channel_tiled"]["pass"]:
        raise RuntimeError(f"spconv adapter fidelity failed: {report}")
    return report


def run_groupnorm_probes(source: Path, latent: Path) -> dict:
    from trellis.modules import sparse as sp
    from trellis.modules.sparse.norm import SparseGroupNorm32
    import memory_bounded_groupnorm as adapter

    cache = torch.load(latent, map_location="cpu", weights_only=True)
    _, actual_feats = source_coordinates(cache)
    model, _, (name, checkpoint_norm) = find_checkpoint_modules(source)
    channels, groups, eps = checkpoint_norm.num_channels, checkpoint_norm.num_groups, checkpoint_norm.eps
    rows = 131072
    base = actual_feats.repeat((rows + len(actual_feats) - 1) // len(actual_feats), 1)[:rows]
    values = base.repeat(1, channels // base.shape[1])
    # Batches are intentionally non-uniform and contiguous, matching SparseTensor's contract.
    batch_sizes = [50000, rows - 50000]
    coords = torch.zeros((rows, 4), dtype=torch.int32)
    coords[:batch_sizes[0], 0] = 0; coords[batch_sizes[0]:, 0] = 1
    coords[:, 1] = torch.arange(rows, dtype=torch.int32) % 1024
    coords[:, 2] = (torch.arange(rows, dtype=torch.int32) // 1024) % 128
    coords[:, 3] = torch.arange(rows, dtype=torch.int32) % 64
    layouts = [slice(0, batch_sizes[0]), slice(batch_sizes[0], rows)]
    rows_report = []
    for dtype in (torch.float16, torch.float32):
        for affine in (False, True):
            weight = checkpoint_norm.weight.detach().cuda().float() if affine else None
            bias = checkpoint_norm.bias.detach().cuda().float() if affine else None
            original = SparseGroupNorm32(groups, channels, eps=eps, affine=affine).cuda().eval()
            if affine:
                original.weight.data.copy_(weight); original.bias.data.copy_(bias)
            features = values.to(dtype=dtype, device="cuda")
            sparse = sp.SparseTensor(feats=features, coords=coords.cuda(), shape=torch.Size([2, channels]), layout=layouts)
            with torch.inference_mode():
                expected_1 = original(sparse).feats
                expected_2 = original(sparse).feats
                actual = adapter.streaming_group_norm(features, layouts, groups, weight, bias, eps, chunk_rows=16384)
                torch.cuda.synchronize()
            repeat = metrics(expected_1, expected_2)
            limits = tolerance(dtype, repeat)
            delta = metrics(expected_1, actual)
            row = {"dtype": str(dtype), "affine": affine, "batch_sizes": batch_sizes,
                   "channels": channels, "groups": groups, "eps": eps,
                   "checkpoint_module": name, "original_repeat": repeat,
                   "tolerance": limits, "adapter": delta, "pass": judged(delta, limits)}
            if not row["pass"]:
                raise RuntimeError(f"GroupNorm fidelity failed: {row}")
            rows_report.append(row)
            del expected_1, expected_2, actual, sparse, features, original
            torch.cuda.empty_cache()
    del model
    return {"production_like_rows": rows, "coordinate_source": "saved 29354 feature values, deterministic two-batch layout",
            "cases": rows_report}


def compare_saved_artifacts(reference: Path, candidate: Path) -> dict:
    ref = torch.load(reference, map_location="cpu", weights_only=True)
    got = torch.load(candidate, map_location="cpu", weights_only=True)
    keys = ("vertices", "faces", "vertex_attrs", "vertex_physics")
    if set(ref) != set(got) or set(ref) != set(keys):
        raise RuntimeError("raw mesh tensor schema mismatch")
    rows = {}
    for key in keys:
        if ref[key] is None or got[key] is None:
            if ref[key] is not got[key]:
                raise RuntimeError(f"optional tensor mismatch: {key}")
            rows[key] = {"both_none": True}; continue
        if key == "faces":
            rows[key] = {"shape": list(ref[key].shape), "exact": bool(torch.equal(ref[key], got[key]))}
            if not rows[key]["exact"]:
                raise RuntimeError("face indices differ in child-process comparison")
        else:
            rows[key] = metrics(ref[key], got[key])
    return {"reference": str(reference), "candidate": str(candidate), "tensors": rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("operations", "compare-artifacts"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--latent", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "operations":
        if not args.latent: raise SystemExit("--latent is required")
        result = {"channel_and_output_tiling": run_conv_probes(args.source, args.latent),
                  "memory_bounded_groupnorm": run_groupnorm_probes(args.source, args.latent)}
    else:
        if not args.reference or not args.candidate: raise SystemExit("--reference/--candidate are required")
        result = compare_saved_artifacts(args.reference, args.candidate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": "success", "output": str(args.output)}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
