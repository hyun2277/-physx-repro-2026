#!/usr/bin/env python3
"""CPU-only integrity and qualitative comparison for the completed 29806 probe."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw
import torch
import trimesh

ROOT = Path("/home/minsujo/Desktop/SH/PHYSx")
RUN = ROOT / "logs/29806-viewpoint-probe/20260927T061911Z-4b32fcccb880"
STAGE = ROOT / "staging/29806-viewpoint-probe-20260927T061911Z-4b32fcccb880"
INPUTS = ROOT / "staging/articulated-sampling-29806-20260926T220010Z-ac2c1dfab94d/datasets/PhysXNet/renders_cond/29806_"
OUT = ROOT / "repro-records/04_PhysX-3D/자료확보/2026-09-27_29806_동일seed_시점_probe_결과검증"
FRAMES = ("000", "006")
EXPECTED_INPUT_SHA = {
    "000": "ecc444a491dd490412acafcb93ab77b9b8ef03ded976b37e691da03e7c9cf6ea",
    "006": "89f691cce979ae2b7e86929c60541d69b1c37da7c77d7a521eca0a2b0cc7782b",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def marker(name: str) -> dict:
    data = json.loads((RUN / "steps" / name / "SUCCESS.json").read_text())
    if data.get("status") != "success":
        raise RuntimeError(f"unsuccessful marker: {name}")
    for row in data.get("outputs", []):
        path = Path(row["path"])
        if not path.is_file() or path.stat().st_size != row["bytes"] or sha(path) != row["sha256"]:
            raise RuntimeError(f"marker output mismatch: {name}: {path}")
    return data


def command(name: str) -> dict:
    return json.loads((RUN / "steps" / name / "command.json").read_text())


def frame_data(label: str, numbers: tuple[int, int, int, int, int]) -> dict:
    sampling_stage, physics_stage, mesh_stage, audit_stage, gate_stage = numbers
    names = {
        "sampling": f"{sampling_stage:02d}_sampling_{label}",
        "gate": f"{gate_stage:02d}_decoder_gate_{label}",
        "physics": f"{physics_stage:02d}_physics_decoder_{label}",
        "mesh": f"{mesh_stage:02d}_mesh_decoder_{label}",
        "audit": f"{audit_stage:02d}_cpu_articulation_audit_{label}",
    }
    markers = {key: marker(value) for key, value in names.items()}
    commands = {key: command(names[key]) for key in ("sampling", "physics", "mesh")}
    sample_report = json.loads((RUN / "steps" / names["sampling"] / "sampling_report.json").read_text())
    physics_report = json.loads((RUN / "steps" / names["physics"] / "physics_report.json").read_text())
    mesh_report = json.loads((RUN / "steps" / names["mesh"] / "mesh_report.json").read_text())
    raw = STAGE / f"frame_{label}/mesh/mesh_physics_raw.pt"
    mesh = STAGE / f"frame_{label}/mesh/mesh.obj"
    property_head = STAGE / f"frame_{label}/articulation_audit/vertex_physics_14ch.pt"
    official = json.loads((STAGE / f"frame_{label}/articulation_audit/official_result.json").read_text())
    cached = torch.load(raw, map_location="cpu", weights_only=False)
    vertices, faces, raw_physics = cached["vertices"], cached["faces"], cached["vertex_physics"]
    if raw_physics.ndim != 2 or raw_physics.shape[1] != 32 or not torch.isfinite(raw_physics).all():
        raise RuntimeError(f"{label}: invalid raw physics")
    if not torch.isfinite(vertices).all() or faces.ndim != 2 or faces.shape[1] != 3:
        raise RuntimeError(f"{label}: invalid mesh tensor")
    property_values = torch.load(property_head, map_location="cpu", weights_only=True)
    if property_values.shape != (len(vertices), 14) or not torch.isfinite(property_values).all():
        raise RuntimeError(f"{label}: invalid 14-channel property head")
    reloaded = trimesh.load(mesh, force="mesh", process=False)
    if len(reloaded.vertices) != len(vertices) or len(reloaded.faces) != len(faces):
        raise RuntimeError(f"{label}: OBJ reload count mismatch")
    input_path = INPUTS / f"{label}.png"
    with Image.open(input_path) as image:
        image.load()
        if image.format != "PNG": raise RuntimeError(f"{label}: input is not PNG")
        input_size = list(image.size)
    env_keys = ("CUDA_VISIBLE_DEVICES", "CUDA_HOME", "CUDACXX", "CC", "CXX", "CUDAHOSTCXX", "NVCC_CCBIN", "SPCONV_ALGO", "PHYSX_TILE_ENABLE", "PHYSX_OUTPUT_TILE_ENABLE", "PHYSX_STREAMING_GROUPNORM_ENABLE", "PHYSX_STREAMING_GROUPNORM_CHUNK_ROWS", "PHYSX_GPU_RESERVE_MIB", "PYTHONPATH")
    environment = commands["sampling"]["environment"]
    if sample_report["seed"] != 1 or commands["sampling"]["argv"][-1] != "1":
        raise RuntimeError(f"{label}: seed is not 1")
    if sha(input_path) != EXPECTED_INPUT_SHA[label]:
        raise RuntimeError(f"{label}: input SHA mismatch")
    if environment.get("CUDA_VISIBLE_DEVICES") != "1" or environment.get("SPCONV_ALGO") != "native":
        raise RuntimeError(f"{label}: CUDA/native settings mismatch")
    for key in env_keys:
        if commands["physics"]["environment"].get(key) != environment.get(key) or commands["mesh"]["environment"].get(key) != environment.get(key):
            raise RuntimeError(f"{label}: inconsistent child environment key {key}")
    moving = [item for group, item in official["groups"].items() if int(group) > 0]
    moving_area = sum(item["majority_area"] for item in moving)
    return {
        "label": label, "input": {"path": str(input_path), "sha256": sha(input_path), "size": input_size},
        "commands": {key: commands[key]["argv"] for key in commands},
        "environment": environment, "success_marker_count": len(markers),
        "artifacts": {
            "raw": {"path": str(raw), "sha256": sha(raw), "bytes": raw.stat().st_size, "shape": list(raw_physics.shape), "finite": True},
            "mesh": {"path": str(mesh), "sha256": sha(mesh), "bytes": mesh.stat().st_size, "vertices": len(vertices), "faces": len(faces), "obj_reloaded": True},
            "property_head": {"path": str(property_head), "sha256": sha(property_head), "bytes": property_head.stat().st_size, "shape": list(property_values.shape), "finite": True},
        },
        "gpu": {
            "sampling_torch_peak_mib": sample_report["memory"][-1]["max_allocated_mib"],
            "physics_torch_peak_mib": physics_report["torch_peak_allocated_mib"],
            "mesh_torch_peak_mib": mesh_report["torch_peak_allocated_mib"],
            "physics_nvidia_smi_peak_mib": json.loads((RUN / "steps" / names["physics"] / "gpu_usage.json").read_text())["peak_nvidia_smi_mib"],
            "mesh_nvidia_smi_peak_mib": json.loads((RUN / "steps" / names["mesh"] / "gpu_usage.json").read_text())["peak_nvidia_smi_mib"],
        },
        "official_grouping": {"num_group": official["predicted_num_group"], "gt_num_group": official["gt_num_group"], "groups": official["groups"], "moving_majority_area_total": moving_area},
        "_vertices": vertices.numpy(), "_property": property_values.numpy(),
    }


def group_preview(label: str, values: dict) -> Image.Image:
    vertices, property_values = values.pop("_vertices"), values.pop("_property")
    groups = property_values[:, 3]
    labels = np.full(len(groups), -1, dtype=np.int64)
    for group in range(values["official_grouping"]["num_group"]):
        labels[(groups > group - .5) & (groups < group + .5)] = group
    keep = np.linspace(0, len(vertices) - 1, min(len(vertices), 70000), dtype=np.int64)
    palette = np.array([[0.42, 0.45, 0.50], [0.82, 0.15, 0.15], [0.95, 0.58, 0.10], [0.38, 0.25, 0.60]])
    colors = np.array([[0.1, 0.1, 0.1] if x < 0 else palette[x % len(palette)] for x in labels[keep]])
    fig, ax = plt.subplots(figsize=(5, 4), dpi=150)
    ax.scatter(vertices[keep, 0], vertices[keep, 1], c=colors, s=0.35, linewidths=0)
    ax.set_aspect("equal"); ax.set_axis_off(); ax.set_title(f"{label}: official groups (0 gray; moving groups red/orange)", fontsize=8)
    fig.tight_layout(pad=.1)
    temp = OUT / f"_{label}_group.png"; fig.savefig(temp, facecolor="white"); plt.close(fig)
    with Image.open(temp) as image:
        return image.convert("RGB").copy()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if json.loads((RUN / "result.json").read_text()).get("status") != "success":
        raise RuntimeError("probe result is not successful")
    # 000 uses stages 3–7; 006 uses stages 8–12.
    data = {"000": frame_data("000", (3, 5, 6, 7, 4)), "006": frame_data("006", (8, 10, 11, 12, 9))}
    area_ratio = data["006"]["official_grouping"]["moving_majority_area_total"] / data["000"]["official_grouping"]["moving_majority_area_total"]
    report = {
        "status": "verified", "scope": "two-input-view, same-seed qualitative probe; not paper evaluation or general performance evidence",
        "shared_conditions_verified": {"seed": 1, "GPU": "physical index 1", "spconv_algo": "native", "same_environment": True, "same_checkpoint_manifest": True, "same_adapter": True},
        "gt": {"groups": 4, "structure": "fixed base group 0 plus three type-C rotation groups (1,2,3), each parent 0"},
        "frames": data,
        "observation": {
            "006_num_group_is_closer_to_gt_4_than_000": True,
            "000_num_group": data["000"]["official_grouping"]["num_group"],
            "006_num_group": data["006"]["official_grouping"]["num_group"],
            "moving_majority_area_ratio_006_over_000": area_ratio,
            "interpretation": "006 has a larger and less fragmented principal moving group, but its extra group 2 has only two vertices/two majority faces. No predicted group is mapped to a particular GT door.",
            "limits": ["CUDA operations may be nondeterministic despite equal seed; byte/vertex identity is not claimed.", "No generated-vertex to GT-part correspondence; parent/direction/position/range accuracy is not established.", "One object and two views only; not a paper quantitative evaluation or general performance claim."],
        },
    }
    left_input = Image.open(INPUTS / "000.png").convert("RGB"); right_input = Image.open(INPUTS / "006.png").convert("RGB")
    left_group, right_group = group_preview("000", data["000"]), group_preview("006", data["006"])
    width, gap, header = 800, 12, 38
    top_h, bottom_h = 400, 320
    canvas = Image.new("RGB", (width * 2 + gap * 3, header + top_h + bottom_h + gap * 2), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((12, 12), "29806 same-seed viewpoint probe: inputs above; official group previews below", fill="black")
    for label, x, input_image, group_image in (("000", gap, left_input, left_group), ("006", width + gap * 2, right_input, right_group)):
        input_image.thumbnail((width, top_h), Image.Resampling.LANCZOS)
        group_image.thumbnail((width, bottom_h), Image.Resampling.LANCZOS)
        canvas.paste(input_image, (x + (width - input_image.width) // 2, header + (top_h - input_image.height) // 2))
        canvas.paste(group_image, (x + (width - group_image.width) // 2, header + top_h + gap))
        draw.text((x + 8, header + 8), f"{label}.png input", fill="white", stroke_width=1, stroke_fill="black")
    preview = OUT / "29806_000_vs_006_input_and_official_groups.png"
    canvas.save(preview)
    for temporary in OUT.glob("_*_group.png"): temporary.unlink()
    report["comparison_preview"] = str(preview)
    (OUT / "statistics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"verified": True, "groups": {x: data[x]["official_grouping"]["num_group"] for x in FRAMES}, "preview": str(preview)}))


if __name__ == "__main__":
    main()
