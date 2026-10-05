"""Small, Isaac-independent helpers used by every 29806 GUI runner mode."""

import json
import math
import os
from pathlib import Path


def json_compatible(value, path="$"):
    """Convert supported USD/scientific values and name unsupported paths."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite JSON number at {path}: {value!r}")
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                kind = f"{type(key).__module__}.{type(key).__qualname__}"
                raise TypeError(f"unsupported JSON key at {path}: {kind}")
            result[key] = json_compatible(item, f"{path}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [json_compatible(item, f"{path}[{index}]") for index, item in enumerate(value)]

    module = type(value).__module__
    name = type(value).__qualname__
    if module.startswith("numpy"):
        if hasattr(value, "tolist"):
            return json_compatible(value.tolist(), path)
        if hasattr(value, "item"):
            return json_compatible(value.item(), path)
    if module.startswith("pxr.Sdf") and name == "Path":
        return str(value)
    if module.startswith("pxr.Gf"):
        if name.startswith("Quat"):
            imaginary = value.GetImaginary()
            values = [value.GetReal(), *[imaginary[index] for index in range(len(imaginary))]]
        else:
            try:
                values = [value[index] for index in range(len(value))]
            except (TypeError, AttributeError):
                values = None
        if values is not None:
            return [json_compatible(item, f"{path}[{index}]") for index, item in enumerate(values)]
    raise TypeError(f"unsupported JSON value at {path}: {module}.{name}")


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    normalized = json_compatible(value)
    temporary.write_text(json.dumps(normalized, indent=2, allow_nan=False) + "\n")
    os.replace(temporary, path)


def corners(bounds):
    lo, hi = bounds["min"], bounds["max"]
    return [[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]


def validate_modes(*, static_mapping_gate=False, initialization_diagnostic=False,
                   initialization_isolation_diagnostic=False, gated_recovery_end_to_end=False,
                   diffuse_only_material_diagnostic=False):
    selected = [name for name, enabled in (
        ("static_mapping", static_mapping_gate),
        ("initialization", initialization_diagnostic),
        ("isolation", initialization_isolation_diagnostic),
        ("recovery_video", gated_recovery_end_to_end),
    ) if enabled]
    if len(selected) > 1:
        raise ValueError("mutually exclusive 29806 modes: " + ", ".join(selected))
    if diffuse_only_material_diagnostic and not initialization_isolation_diagnostic:
        raise ValueError("diffuse-only material diagnostic requires initialization isolation mode")
    return selected[0] if selected else "default_video"


def execution_plan(mode, *, diffuse_only=False):
    plans = {
        "static_mapping": ["stage", "linked_clones", "static_pixel_gate", "human_review_window"],
        "initialization": ["stage", "linked_clones", "prephysics_gate", "physics_initialize", "tensor_view", "bounded_steps"],
        "isolation": ["stage", "linked_clones", "prephysics_gate", "fabric_setup", "physics_initialize", "tensor_view", "visibility_isolation", "closed_steps_1_2_5_10"],
        "recovery_video": ["stage", "linked_clones", "prephysics_gate", "physics_initialize", "tensor_view", "strict_recovery", "closed_hold", "recorder", "three_door_schedule", "video_validation"],
        "default_video": ["stage", "linked_clones", "prephysics_gate", "physics_initialize", "tensor_view", "closed_settle", "recorder", "three_door_schedule", "video_validation"],
    }
    if mode not in plans:
        raise ValueError(f"unknown mode: {mode}")
    result = list(plans[mode])
    if diffuse_only:
        result.insert(result.index("prephysics_gate") + 1, "diffuse_and_emissive_controls")
    return result


def diffuse_pixel_decision(cyan_count, nonblack_ratio, components, *, binding_pass=True):
    component_pass = all(
        row.get("intersects_frame", False)
        and row.get("cyan_pixels", 0) >= 5
        and row.get("nonblack_ratio", 0.0) >= 0.001
        for row in components.values()
    )
    return bool(binding_pass and cyan_count >= 30 and nonblack_ratio >= 0.001 and component_pass)


def internal_exit_payload(*, status, code, mode, plan, completed, asset_pass=False, error=None, last_phase=None):
    payload = {
        "status": status,
        "python_return_code": code,
        "asset_pass": asset_pass,
        "mode": mode,
        "completed_phases": list(completed),
        "unexecuted_phases": [phase for phase in plan if phase not in completed],
    }
    if error is not None:
        payload["primary_error"] = error
    if last_phase is not None:
        payload["last_phase"] = last_phase
    return payload
