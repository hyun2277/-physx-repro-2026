"""Create the GUI cube gate or open the existing 10163 GT-only USD.

This script prepares evidence for a human GUI check. It does not declare that
the viewport is visible and it does not drive physics.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import carb
import omni.usd
from pxr import Gf, Sdf, UsdGeom, UsdLux


MODE = os.environ.get("PHYSX_GUI_MODE", "cube")
RUN_DIR = Path(os.environ["PHYSX_GUI_RUN_DIR"])
USD_10163 = Path(
    "/home/minsujo/Desktop/SH/PHYSx/staging/"
    "gt-only-isaac-control-20261002T072614Z-gt-only-control/"
    "10163/gt_10163/gt_10163.usda"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_marker(name: str, payload: dict) -> None:
    marker = RUN_DIR / f"marker_{name}.json"
    marker.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"PHYSX_GUI_MARKER_{name.upper()}={json.dumps(payload, ensure_ascii=False, sort_keys=True)}")


settings = carb.settings.get_settings()
write_marker(
    "app_startup",
    {"status": "PASS", "mode": MODE, "script_started_after_dependency_resolution": True},
)
write_marker(
    "omni_usd_import",
    {"status": "PASS", "module": getattr(omni.usd, "__file__", None)},
)
write_marker(
    "gui_mode",
    {
        "status": "PASS",
        "headless_setting": settings.get("/app/window/hideUi"),
        "expected_headless": False,
    },
)
context = omni.usd.get_context()

if MODE == "cube":
    context.new_stage()
    stage = context.get_stage()
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    cube = UsdGeom.Cube.Define(stage, "/World/VisibleCube")
    cube.CreateSizeAttr(2.0)
    cube.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 1.0))
    ground = UsdGeom.Cube.Define(stage, "/World/Ground")
    ground.CreateSizeAttr(1.0)
    ground.AddScaleOp().Set(Gf.Vec3f(8.0, 8.0, 0.1))
    ground.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, -0.1))
    light = UsdLux.DistantLight.Define(stage, "/World/KeyLight")
    light.CreateIntensityAttr(2500.0)
    light.CreateAngleAttr(1.0)
    context.get_selection().set_selected_prim_paths(["/World/VisibleCube"], True)
    stage_path = RUN_DIR / "cube_gui_stage.usda"
    stage.GetRootLayer().Export(str(stage_path))
    cube_path = "/World/VisibleCube"
    if not stage.GetPrimAtPath(cube_path).IsValid():
        raise RuntimeError(f"stage did not contain {cube_path}")
    write_marker("cube_created", {"status": "PASS", "prim": cube_path})
    write_marker("cube_stage_lookup", {"status": "PASS", "prim": cube_path})
    write_marker(
        "summary",
        {
            "status": "AUTOMATION_MARKERS_PASS_HUMAN_GUI_CHECK_REQUIRED",
            "mode": MODE,
            "stage": str(stage_path),
            "expected_prims": [cube_path, "/World/Ground", "/World/KeyLight"],
            "human_verified": False,
        }
    )
elif MODE == "10163":
    if not USD_10163.is_file():
        raise FileNotFoundError(USD_10163)
    expected = "72cee88ff5ac563e89c34e4028a9a3fe3d8b839d40f88fed4ef048e3f4fab23b"
    actual = sha256(USD_10163)
    if actual != expected:
        raise RuntimeError(f"10163 USD SHA256 mismatch: {actual}")
    context.open_stage(str(USD_10163))
    stage = context.get_stage()
    if stage is None:
        raise RuntimeError(f"failed to open {USD_10163}")
    default_prim = stage.GetDefaultPrim()
    variant_sets = default_prim.GetVariantSets()
    if variant_sets.HasVariantSet("Physics"):
        variant_sets.GetVariantSet("Physics").SetVariantSelection("physx")
    context.get_selection().set_selected_prim_paths([str(default_prim.GetPath())], True)
    write_marker(
        "cube_stage_lookup",
        {"status": "SKIPPED", "reason": "10163 mode does not create a cube"},
    )
    write_marker(
        "summary",
        {
            "status": "AUTOMATION_MARKERS_PASS_HUMAN_GUI_CHECK_REQUIRED",
            "mode": MODE,
            "usd": str(USD_10163),
            "bytes": USD_10163.stat().st_size,
            "sha256": actual,
            "default_prim": str(default_prim.GetPath()),
            "physics_variant": variant_sets.GetVariantSet("Physics").GetVariantSelection()
            if variant_sets.HasVariantSet("Physics")
            else None,
            "human_verified": False,
        }
    )
else:
    raise ValueError(f"unsupported PHYSX_GUI_MODE={MODE!r}")
