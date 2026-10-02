"""Open and inspect the existing 10163 GT-only USD without simulating it."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import carb
import omni.kit.app
import omni.timeline
import omni.usd
from omni.kit.viewport.utility import frame_viewport_prims, get_active_viewport
from pxr import Usd, UsdPhysics


RUN_DIR = Path(os.environ["PHYSX_GUI_RUN_DIR"])
INPUT_USD = Path(
    "/home/minsujo/Desktop/SH/PHYSx/staging/"
    "gt-only-isaac-control-20261002T072614Z-gt-only-control/"
    "10163/gt_10163/gt_10163.usda"
)
EXPECTED_SHA256 = "72cee88ff5ac563e89c34e4028a9a3fe3d8b839d40f88fed4ef048e3f4fab23b"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def marker(name: str, payload: dict) -> None:
    (RUN_DIR / f"marker_{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"PHYSX_GUI_MARKER_{name.upper()}={json.dumps(payload, ensure_ascii=False, sort_keys=True)}")


def quat_values(value) -> list[float]:
    imaginary = value.GetImaginary()
    return [float(value.GetReal()), float(imaginary[0]), float(imaginary[1]), float(imaginary[2])]


settings = carb.settings.get_settings()
marker("app_startup", {"status": "PASS", "scope": "10163 GT-only static GUI inspection"})
marker("omni_usd_import", {"status": "PASS", "module": getattr(omni.usd, "__file__", None)})
marker(
    "gui_mode",
    {"status": "PASS", "headless_setting": settings.get("/app/window/hideUi"), "expected_headless": False},
)

actual_hash = digest(INPUT_USD)
if actual_hash != EXPECTED_SHA256:
    raise RuntimeError(f"10163 USD SHA256 mismatch: {actual_hash}")
marker(
    "usd_verified",
    {"status": "PASS", "path": str(INPUT_USD), "bytes": INPUT_USD.stat().st_size, "sha256": actual_hash},
)

context = omni.usd.get_context()
context.open_stage(str(INPUT_USD))
stage = context.get_stage()
if stage is None:
    raise RuntimeError(f"failed to open {INPUT_USD}")
root = stage.GetDefaultPrim()
if not root.IsValid():
    raise RuntimeError("10163 stage has no valid default prim")
marker("stage_open", {"status": "PASS", "default_prim": str(root.GetPath())})

variants = root.GetVariantSets()
if not variants.HasVariantSet("Physics"):
    raise RuntimeError("10163 root has no Physics variant set")
physics_variant = variants.GetVariantSet("Physics")
physics_variant.SetVariantSelection("physx")
if physics_variant.GetVariantSelection() != "physx":
    raise RuntimeError("failed to select Physics=physx")
marker("physics_variant", {"status": "PASS", "selection": "physx"})

predicate = Usd.TraverseInstanceProxies(Usd.PrimDefaultPredicate)
prims = list(Usd.PrimRange(stage.GetPseudoRoot(), predicate))
revolute = [p for p in prims if p.IsA(UsdPhysics.RevoluteJoint)]
articulation = [p for p in prims if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
rigid = [p for p in prims if p.HasAPI(UsdPhysics.RigidBodyAPI)]
colliders = [p for p in prims if p.HasAPI(UsdPhysics.CollisionAPI)]
if len(revolute) != 1 or revolute[0].GetName() != "gt_C_1":
    raise RuntimeError(f"expected one gt_C_1 revolute joint, got {[str(p.GetPath()) for p in revolute]}")
if not articulation or not rigid or not colliders:
    raise RuntimeError(
        f"missing static structure: articulation={len(articulation)} rigid={len(rigid)} collider={len(colliders)}"
    )

joint_prim = revolute[0]
joint = UsdPhysics.RevoluteJoint(joint_prim)
joint_data = {
    "status": "PASS",
    "path": str(joint_prim.GetPath()),
    "name": joint_prim.GetName(),
    "body0": [str(x) for x in joint.GetBody0Rel().GetTargets()],
    "body1": [str(x) for x in joint.GetBody1Rel().GetTargets()],
    "axis": str(joint.GetAxisAttr().Get()),
    "local_pos0": list(joint.GetLocalPos0Attr().Get()),
    "local_pos1": list(joint.GetLocalPos1Attr().Get()),
    "local_rot0_wxyz": quat_values(joint.GetLocalRot0Attr().Get()),
    "local_rot1_wxyz": quat_values(joint.GetLocalRot1Attr().Get()),
    "lower_limit_degrees": float(joint.GetLowerLimitAttr().Get()),
    "upper_limit_degrees": float(joint.GetUpperLimitAttr().Get()),
}
marker("joint_structure", joint_data)
marker(
    "schema_counts",
    {
        "status": "PASS",
        "revolute_joint_count": len(revolute),
        "articulation_root_count": len(articulation),
        "rigid_body_count": len(rigid),
        "collider_count_including_instance_proxies": len(colliders),
        "articulation_paths": [str(p.GetPath()) for p in articulation],
        "rigid_body_paths": [str(p.GetPath()) for p in rigid],
        "collider_paths": [str(p.GetPath()) for p in colliders],
    },
)

# Frame the GT geometry first, then select the joint so Stage/Property panels
# expose its authored fields without writing transforms or starting a timeline.
viewport = get_active_viewport()
if viewport is None:
    raise RuntimeError("active viewport was not available")
frame_viewport_prims(viewport, prims=[str(root.GetPath())])
context.get_selection().set_selected_prim_paths([str(joint_prim.GetPath())], True)

app = omni.kit.app.get_app()
ext_manager = app.get_extension_manager()
physics_ext_state = {
    name: bool(ext_manager.is_extension_enabled(name))
    for name in ("omni.physx", "omni.physics.physx", "omni.physics.tensors", "isaacsim.core.simulation_manager")
}
timeline_playing = bool(omni.timeline.get_timeline_interface().is_playing())
if any(physics_ext_state.values()) or timeline_playing:
    raise RuntimeError(f"physics execution guard failed: extensions={physics_ext_state}, timeline={timeline_playing}")
marker(
    "physics_steps",
    {
        "status": "PASS",
        "simulation_steps_requested": 0,
        "timeline_playing": timeline_playing,
        "physics_extensions_enabled": physics_ext_state,
        "physics_scene_created": False,
        "simulation_manager_called": False,
        "tensor_control_called": False,
    },
)
marker(
    "summary",
    {
        "status": "AUTOMATION_MARKERS_PASS_HUMAN_GUI_CHECK_REQUIRED",
        "scope": "GPU 0 GUI display-only, GT-only static USD inspection; not AI prediction",
        "human_verified": False,
        "selected_prim": str(joint_prim.GetPath()),
        "physics_steps": 0,
    },
)
