#!/usr/bin/env python3
"""Run the official image conditioning and samplers, then stop before decoding."""

import argparse
import gc
import json
import os
from pathlib import Path
import time

import numpy as np
from PIL import Image
import torch


def memory(label):
    row = {
        "label": label,
        "allocated_mib": round(torch.cuda.memory_allocated() / 2**20, 3),
        "reserved_mib": round(torch.cuda.memory_reserved() / 2**20, 3),
        "max_allocated_mib": round(torch.cuda.max_memory_allocated() / 2**20, 3),
        "max_reserved_mib": round(torch.cuda.max_memory_reserved() / 2**20, 3),
    }
    print(json.dumps({"gpu_memory": row}), flush=True)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    source = Path(args.source).resolve()
    output = Path(args.output).resolve()
    report_path = Path(args.report).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "started": time.time(), "seed": args.seed,
        "scope": "official preprocess + conditioning + sparse/slat/physics sampling; no decoder",
        "spconv_algo_requested": os.environ.get("SPCONV_ALGO"), "memory": [],
    }

    from trellis.pipelines import TrellisImageTo3DPipeline
    from trellis.modules.sparse import conv as sparse_conv

    report["spconv_algo_actual"] = sparse_conv.SPCONV_ALGO
    if report["spconv_algo_requested"] != "native" or report["spconv_algo_actual"] != "native":
        raise RuntimeError("SPCONV_ALGO native must be selected before trellis import")
    pipeline = TrellisImageTo3DPipeline.from_pretrained(str(source / "pretrain/diffusion"))
    removed = []
    for name in ("slat_decoder_phy", "slat_decoder_mesh", "slat_decoder_gs",
                 "slat_decoder_rf", "slat_decoder_output"):
        if name in pipeline.models:
            del pipeline.models[name]
            removed.append(name)
    gc.collect()
    pipeline.cuda()
    report["not_loaded_on_gpu"] = removed
    torch.cuda.reset_peak_memory_stats()
    report["memory"].append(memory("sampling_models_loaded"))

    image = Image.open(args.input)
    processed = pipeline.preprocess_image(image)
    processed.save(output / "preprocessed.png")
    pixels = np.asarray(processed)
    foreground = np.argwhere(np.any(pixels != 0, axis=2))
    if len(foreground) == 0:
        raise RuntimeError("empty preprocessed foreground")
    report["preprocessed"] = {
        "size": list(processed.size), "pixel_min": int(pixels.min()),
        "pixel_max": int(pixels.max()), "foreground_pixels": int(len(foreground)),
        "foreground_bbox_yx": [foreground.min(0).tolist(), foreground.max(0).tolist()],
    }
    with torch.inference_mode():
        cond = pipeline.get_cond([processed])
        torch.manual_seed(args.seed)
        coords = pipeline.sample_sparse_structure(cond, 1, {})
        slat, phy = pipeline.sample_slat(cond, coords, {})
        torch.cuda.synchronize()
    if not torch.equal(slat.coords, phy.coords):
        raise RuntimeError("geometry and physics latent coordinates differ")
    for name, value in (("slat", slat.feats), ("physics", phy.feats)):
        if value.ndim != 2 or value.shape[1] != 8 or not torch.isfinite(value).all().item():
            raise RuntimeError(f"invalid {name} latent")
    unique = torch.unique(slat.coords, dim=0)
    if len(unique) != len(slat.coords):
        raise RuntimeError("duplicate sparse coordinates")
    cache = {
        "slat_coords": slat.coords.detach().cpu().to(torch.int32),
        "slat_feats": slat.feats.detach().cpu().float(),
        "phy_coords": phy.coords.detach().cpu().to(torch.int32),
        "phy_feats": phy.feats.detach().cpu().float(),
        "cpu_rng": torch.get_rng_state().cpu(),
        "cuda_rng": [x.cpu() for x in torch.cuda.get_rng_state_all()],
    }
    torch.save(cache, output / "sampled_latents.pt")
    report["latent"] = {
        "rows": len(cache["slat_coords"]), "feature_shape": list(cache["slat_feats"].shape),
        "coordinate_shape": list(cache["slat_coords"].shape),
        "coordinate_min": cache["slat_coords"].min(0).values.tolist(),
        "coordinate_max": cache["slat_coords"].max(0).values.tolist(),
        "coordinate_unique": len(unique), "coordinate_equal": True,
        "feature_dtype": str(cache["slat_feats"].dtype), "finite": True,
    }
    report["memory"].append(memory("sampling_complete"))
    report["finished"] = time.time()
    report["status"] = "success"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"sampling_complete": True, **report["latent"]}), flush=True)


if __name__ == "__main__":
    main()
