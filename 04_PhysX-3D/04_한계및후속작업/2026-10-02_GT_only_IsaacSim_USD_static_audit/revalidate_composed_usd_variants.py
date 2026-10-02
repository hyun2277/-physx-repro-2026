#!/usr/bin/env python3
"""Compose existing importer USD with an explicit Physics variant; no drive."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from isaacsim import SimulationApp

EXPECTED = {"10163": ("physx", 1), "29806": ("physx", 3), "29354": ("physics", 0)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--experience", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = SimulationApp(
        {"headless": True, "active_gpu": 1, "physics_gpu": 1, "multi_gpu": False,
         "extra_args": ["--/renderer/multiGpu/enabled=false", "--/renderer/multiGpu/autoEnable=false"]},
        experience=str(args.experience),
    )
    try:
        import omni.usd
        from pxr import Usd, UsdPhysics

        result = {}
        for oid, (selection, expected) in EXPECTED.items():
            root = args.staging / oid / f"gt_{oid}" / f"gt_{oid}.usda"
            context = omni.usd.get_context()
            context.open_stage(str(root))
            app.update()
            stage = context.get_stage()
            default = stage.GetDefaultPrim()
            variant = default.GetVariantSets().GetVariantSet("Physics")
            if not variant.IsValid() or selection not in variant.GetVariantNames():
                raise RuntimeError(f"{oid}: required Physics variant {selection!r} is unavailable")
            variant.SetVariantSelection(selection)
            app.update()
            revolute = [p for p in Usd.PrimRange(stage.GetPseudoRoot()) if p.IsA(UsdPhysics.RevoluteJoint)]
            generic = [p for p in Usd.PrimRange(stage.GetPseudoRoot()) if p.IsA(UsdPhysics.Joint)]
            articulation = [p for p in Usd.PrimRange(stage.GetPseudoRoot()) if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
            collision = [p for p in Usd.PrimRange(stage.GetPseudoRoot()) if p.HasAPI(UsdPhysics.CollisionAPI)]
            rigid = [p for p in Usd.PrimRange(stage.GetPseudoRoot()) if p.HasAPI(UsdPhysics.RigidBodyAPI)]
            if len(revolute) != expected:
                raise RuntimeError(f"{oid}: expected {expected} revolute joints after Physics={selection}; found {len(revolute)}")
            result[oid] = {
                "usd": str(root), "physics_variant": selection, "revolute_joint_count": len(revolute),
                "generic_joint_count": len(generic), "articulation_root_count": len(articulation),
                "collision_api_count": len(collision), "rigid_body_api_count": len(rigid),
            }
        (args.output / "composed_variant_schema_result.json").write_text(json.dumps(result, indent=2) + "\n")
        print("GT_ONLY_COMPOSED_VARIANT_REVALIDATION=PASS")
        return 0
    finally:
        app.close()


if __name__ == "__main__":
    raise SystemExit(main())
