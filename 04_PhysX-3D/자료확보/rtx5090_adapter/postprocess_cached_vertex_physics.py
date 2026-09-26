#!/usr/bin/env python3
"""CPU-only audit/postprocess of the saved 29354 vertex physics tensor."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/home/minsujo/Desktop/SH/PHYSx/cache/matplotlib")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch


ROOT = Path("/home/minsujo/Desktop/SH/PHYSx")
SOURCE = ROOT / "sources/physx-4f54e750a309"
RAW = (
    ROOT
    / "staging/rtx5090-cached-decoder-29354-20260926T194524Z-d69f74359b60"
    / "mesh_physics_raw.pt"
)
CHECKPOINT = SOURCE / "pretrain/diffusion/ckpts_new/property_output_step0100000.pt"
OUTPUT = (
    ROOT
    / "repro-records/04_PhysX-3D/자료확보/rtx5090_adapter"
    / "2026-09-27_cached-physics-postprocess"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tensor_stats(value: torch.Tensor) -> dict:
    value = value.float()
    return {
        "shape": list(value.shape),
        "dtype": str(value.dtype),
        "finite": bool(torch.isfinite(value).all()),
        "min": float(value.min()),
        "max": float(value.max()),
        "mean": float(value.mean()),
        "std_population": float(value.std(unbiased=False)),
    }


def output_head(features: torch.Tensor, state: dict, name: str) -> torch.Tensor:
    """Evaluate the 3x3 head for a 1x1 input, where only its center is used."""
    weight = state[f"output_layer_{name}.weight"][:, :, 1, 1].float()
    bias = state[f"output_layer_{name}.bias"].float()
    return features.float() @ weight.T + bias


def minmax(value: torch.Tensor) -> torch.Tensor:
    span = value.max() - value.min()
    if not bool(torch.isfinite(span)) or float(span) == 0.0:
        raise RuntimeError("cannot min-max normalize a constant or nonfinite tensor")
    return (value - value.min()) / span


def language_stats(features: torch.Tensor, state: dict, chunk: int = 4096) -> dict:
    count = 0
    total = 0.0
    total_sq = 0.0
    minimum = float("inf")
    maximum = float("-inf")
    finite = True
    for start in range(0, len(features), chunk):
        value = output_head(features[start : start + chunk], state, "lang")
        finite = finite and bool(torch.isfinite(value).all())
        minimum = min(minimum, float(value.min()))
        maximum = max(maximum, float(value.max()))
        total += float(value.double().sum())
        total_sq += float(value.double().square().sum())
        count += value.numel()
    mean = total / count
    return {
        "shape": [len(features), 3072],
        "finite": finite,
        "min": minimum,
        "max": maximum,
        "mean": mean,
        "std_population": max(0.0, total_sq / count - mean * mean) ** 0.5,
    }


def make_preview(vertices: np.ndarray, affordance: np.ndarray, density: np.ndarray, scale: np.ndarray, path: Path) -> None:
    # A deterministic vertex projection, not a camera render or a surface-quality assessment.
    stride = max(1, len(vertices) // 60000)
    selected = slice(None, None, stride)
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), constrained_layout=True)
    for axis, values, title, cmap in (
        (axes[0], affordance, "Affordance heat value [0,1]", "viridis"),
        (axes[1], density, "Density (official 'material') [g/cm³]", "plasma"),
    ):
        points = axis.scatter(
            vertices[selected, 0], vertices[selected, 2], c=values[selected],
            s=0.18, cmap=cmap, linewidths=0,
        )
        axis.set_aspect("equal")
        axis.set_axis_off()
        axis.set_title(title)
        fig.colorbar(points, ax=axis, fraction=0.046, pad=0.03)
    axes[2].hist(scale, bins=80, color="#4472c4")
    axes[2].set_title("Predicted physical scale [cm]")
    axes[2].set_xlabel("cm")
    axes[2].set_ylabel("vertex count")
    fig.suptitle("29354 cached output: CPU vertex-linked preview (not a rendered evaluation view)")
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, default=RAW)
    parser.add_argument("--checkpoint", type=Path, default=CHECKPOINT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    saved = torch.load(args.raw, map_location="cpu", weights_only=False)
    vertices = saved["vertices"].float()
    raw = saved["vertex_physics"].float()
    if raw.ndim != 2 or raw.shape[1] != 32 or len(raw) != len(vertices):
        raise RuntimeError(f"unexpected vertex physics shape: {tuple(raw.shape)}")
    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    expected = {
        "output_layer_lang.weight": [3072, 16, 3, 3],
        "output_layer_lang.bias": [3072],
        "output_layer_phy.weight": [14, 16, 3, 3],
        "output_layer_phy.bias": [14],
    }
    actual = {key: list(state[key].shape) for key in expected}
    if actual != expected:
        raise RuntimeError(f"unexpected checkpoint shapes: {actual}")

    first16 = raw[:, :16]
    last16 = raw[:, 16:]
    physics_normalized = output_head(last16, state, "phy")
    physics = physics_normalized.clone()
    physics[:, 0] = physics[:, 0] * 48 + 95
    physics[:, 2] = physics[:, 2] * 2.8 + 2.3
    physics[:, 4] = physics[:, 4] * 0.732 - 0.812
    physics[:, -1] = physics[:, -1] * 4
    affordance = minmax(physics[:, 1])
    density_heat = minmax(physics[:, 2])

    names = [
        "scale_cm", "affordance_normalized_target", "density_g_cm3", "group_id",
        "parent_group_id", "motion_direction_x", "motion_direction_y",
        "motion_direction_z", "motion_position_x", "motion_position_y",
        "motion_position_z", "motion_range_0", "motion_range_1", "movement_type_code",
    ]
    channels = {str(i): {"name": names[i], **tensor_stats(physics[:, i])} for i in range(14)}
    report = {
        "scope": "CPU-only postprocess of existing cached decoder output; no GPU or decoder execution",
        "inputs": {
            "raw": {"path": str(args.raw), "bytes": args.raw.stat().st_size, "sha256": sha256(args.raw)},
            "property_output_checkpoint": {
                "path": str(args.checkpoint), "bytes": args.checkpoint.stat().st_size,
                "sha256": sha256(args.checkpoint),
            },
        },
        "checkpoint_weight_shapes": actual,
        "raw_split": {
            "training_renderer_language": "channels 0:16",
            "training_renderer_physics": "channels 16:32",
            "official_example_language": "channels 16:32",
            "official_example_physics": "channels 16:32",
            "official_example_inputs_are_identical": bool(torch.equal(raw[:, 16:], raw[:, -16:])),
        },
        "official_example_path": {
            "language_head": language_stats(last16, state),
            "physics_normalized": tensor_stats(physics_normalized),
            "physics_postprocessed_channels": channels,
            "affordance_heat": tensor_stats(affordance),
            "density_heat_named_material_by_example": tensor_stats(density_heat),
            "num_group": round(float(physics[:, 3].max())) + 1,
        },
        "separate_correction_candidate": {
            "language_input": "channels 0:16, following mesh_renderer.py training path",
            "language_head": language_stats(first16, state),
            "description_score_not_computed": "requires a chosen question/question_type and CLIP text embedding; candidate is not treated as official output",
        },
        "preview": "vertex x-z projection for confirmed physics-head affordance/density plus scale histogram",
    }
    stats_path = args.output / "postprocess_stats.json"
    stats_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    make_preview(
        vertices.numpy(), affordance.numpy(), physics[:, 2].numpy(), physics[:, 0].numpy(),
        args.output / "vertex_physics_preview.png",
    )
    print(stats_path)


if __name__ == "__main__":
    main()
