#!/usr/bin/env python3
"""Exercise production JSON conversion with installed USD and NumPy types."""

import json
import math
import tempfile
from pathlib import Path

import numpy as np
from pxr import Gf, Sdf, Usd, UsdShade

from gui_29806_common import atomic_json, json_compatible


def expect_error(value, expected):
    try:
        json_compatible(value)
    except (TypeError, ValueError) as error:
        assert expected in str(error), str(error)
    else:
        raise AssertionError(f"expected failure containing {expected!r}")


def main():
    stage = Usd.Stage.CreateInMemory()
    material = UsdShade.Material.Define(stage, "/Material")
    shader = UsdShade.Shader.Define(stage, "/Material/PreviewSurface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.12, 0.68, 0.92))
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(1.0)
    raw_color = shader.GetInput("diffuseColor").Get()
    assert type(raw_color).__name__ == "Vec3f"
    payload = {"clones": [{
        "diffuseColor": raw_color,
        "opacity": shader.GetInput("opacity").Get(),
        "material": material.GetPath(),
        "numpy_scalar": np.float32(0.25),
        "numpy_array": np.asarray([[1, 2], [3, 4]], dtype=np.int32),
    }]}
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "prephysics_material_binding_audit.json"
        atomic_json(path, payload)
        decoded = json.loads(path.read_text())
    assert decoded["clones"][0]["diffuseColor"] == [float(raw_color[index]) for index in range(3)]
    assert decoded["clones"][0]["material"] == "/Material"
    assert decoded["clones"][0]["numpy_scalar"] == 0.25
    assert decoded["clones"][0]["numpy_array"] == [[1, 2], [3, 4]]
    expect_error({"clones": [{"unsupported": object()}]}, "$.clones[0].unsupported")
    expect_error({"bad": math.inf}, "$.bad")
    print("GUI_29806_INSTALLED_USD_JSON_TYPES_PASS first_original_failure=$.clones[0].diffuseColor type=pxr.Gf.Vec3f")


if __name__ == "__main__":
    main()
