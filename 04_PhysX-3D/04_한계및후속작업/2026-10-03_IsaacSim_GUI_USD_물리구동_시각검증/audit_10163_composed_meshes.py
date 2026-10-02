"""Audit composed 10163 meshes without renderer or physics execution."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

import carb
import omni.kit.app
import omni.usd
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade


INPUT_USD = Path(
    "/home/minsujo/Desktop/SH/PHYSx/staging/"
    "gt-only-isaac-control-20261002T072614Z-gt-only-control/"
    "10163/gt_10163/gt_10163.usda"
)
EXPECTED_SHA256 = "72cee88ff5ac563e89c34e4028a9a3fe3d8b839d40f88fed4ef048e3f4fab23b"
OUTPUT = Path(os.environ["PHYSX_STATIC_AUDIT_OUTPUT"])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def vec(value):
    return [float(x) for x in value]


def matrix(value):
    return [[float(value[row][column]) for column in range(4)] for row in range(4)]


def determinant3(value) -> float:
    a = [[float(value[row][column]) for column in range(3)] for row in range(3)]
    return (
        a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
        - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
        + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0])
    )


def bounds(points):
    if not points:
        return None
    mins = [min(float(p[i]) for p in points) for i in range(3)]
    maxs = [max(float(p[i]) for p in points) for i in range(3)]
    return {"min": mins, "max": maxs, "size": [maxs[i] - mins[i] for i in range(3)]}


def serializable_metadata(prim, key):
    value = prim.GetMetadata(key)
    return None if value is None else str(value)


actual_sha = sha256(INPUT_USD)
if actual_sha != EXPECTED_SHA256:
    raise RuntimeError(f"input hash mismatch: {actual_sha}")

context = omni.usd.get_context()
context.open_stage(str(INPUT_USD))
stage = context.get_stage()
if stage is None:
    raise RuntimeError("failed to compose input stage")
root = stage.GetDefaultPrim()
root.GetVariantSet("Physics").SetVariantSelection("physx")

xforms = UsdGeom.XformCache(Usd.TimeCode.Default())
predicate = Usd.TraverseInstanceProxies(Usd.PrimDefaultPredicate)
mesh_prims = [p for p in Usd.PrimRange(stage.GetPseudoRoot(), predicate) if p.IsA(UsdGeom.Mesh)]
rows = []
for prim in mesh_prims:
    mesh = UsdGeom.Mesh(prim)
    points = list(mesh.GetPointsAttr().Get() or [])
    counts = list(mesh.GetFaceVertexCountsAttr().Get() or [])
    indices = list(mesh.GetFaceVertexIndicesAttr().Get() or [])
    all_point_values = [float(x) for point in points for x in point]
    indices_valid = bool(points) and all(0 <= int(index) < len(points) for index in indices)
    topology_valid = bool(points) and bool(counts) and sum(int(x) for x in counts) == len(indices) and indices_valid
    local_bounds = bounds(points)
    world_transform = xforms.GetLocalToWorldTransform(prim)
    world_points = [world_transform.Transform(Gf.Vec3d(*vec(point))) for point in points]
    imageable = UsdGeom.Imageable(prim)
    display_color = mesh.GetDisplayColorPrimvar()
    display_opacity = mesh.GetDisplayOpacityPrimvar()
    material, material_rel = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
    extent = list(mesh.GetExtentAttr().Get() or [])
    hint = list(UsdGeom.ModelAPI(prim).GetExtentsHint() or [])
    prim_layers = []
    for spec in prim.GetPrimStack():
        path = Path(spec.layer.realPath) if spec.layer.realPath else None
        prim_layers.append(
            {
                "identifier": spec.layer.identifier,
                "real_path": str(path) if path else None,
                "exists": bool(path and path.is_file()),
                "bytes": path.stat().st_size if path and path.is_file() else None,
                "sha256": sha256(path) if path and path.is_file() else None,
            }
        )
    rows.append(
        {
            "path": str(prim.GetPath()),
            "active": bool(prim.IsActive()),
            "loaded": bool(prim.IsLoaded()),
            "instance_proxy": bool(prim.IsInstanceProxy()),
            "visibility_authored": str(imageable.GetVisibilityAttr().Get()),
            "visibility_computed": str(imageable.ComputeVisibility()),
            "purpose_authored": str(imageable.GetPurposeAttr().Get()),
            "purpose_computed": str(imageable.ComputePurpose()),
            "point_count": len(points),
            "face_count": len(counts),
            "face_vertex_index_count": len(indices),
            "triangle_equivalent_count": sum(max(0, int(n) - 2) for n in counts),
            "points_finite": all(math.isfinite(x) for x in all_point_values),
            "topology_valid": topology_valid,
            "local_bounds_from_points": local_bounds,
            "world_bounds_from_transformed_points": bounds(world_points),
            "world_transform": matrix(world_transform),
            "linear_transform_determinant": determinant3(world_transform),
            "extent_authored": [vec(x) for x in extent],
            "extents_hint": [vec(x) for x in hint],
            "orientation": str(mesh.GetOrientationAttr().Get()),
            "subdivision_scheme": str(mesh.GetSubdivisionSchemeAttr().Get()),
            "material_binding": str(material.GetPath()) if material else None,
            "material_relationship": str(material_rel.GetPath()) if material_rel else None,
            "display_color": [vec(x) for x in (display_color.Get() or [])],
            "display_color_interpolation": str(display_color.GetInterpolation()),
            "display_opacity": [float(x) for x in (display_opacity.Get() or [])],
            "display_opacity_interpolation": str(display_opacity.GetInterpolation()),
            "references_metadata": serializable_metadata(prim, "references"),
            "payload_metadata": serializable_metadata(prim, "payload"),
            "resolved_prim_stack_layers": prim_layers,
        }
    )

# Validate the proposed presentation-only binding in the anonymous session
# layer.  This is never exported or saved and does not touch the source asset.
original_target = stage.GetEditTarget()
stage.SetEditTarget(stage.GetSessionLayer())
diagnostic_material = UsdShade.Material.Define(stage, "/__PhysXDiagnostic/Material")
diagnostic_shader = UsdShade.Shader.Define(stage, "/__PhysXDiagnostic/Material/PreviewSurface")
diagnostic_shader.CreateIdAttr("UsdPreviewSurface")
diagnostic_shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.15, 0.65, 0.95))
diagnostic_shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(1.0)
diagnostic_shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
diagnostic_material.CreateSurfaceOutput().ConnectToSource(diagnostic_shader.ConnectableAPI(), "surface")
geometry_prim = stage.GetPrimAtPath("/gt_10163/Geometry")
UsdShade.MaterialBindingAPI.Apply(geometry_prim).Bind(diagnostic_material)
diagnostic_bound_paths = []
for mesh_prim in mesh_prims:
    bound = UsdShade.MaterialBindingAPI(mesh_prim).ComputeBoundMaterial()[0]
    diagnostic_bound_paths.append(str(bound.GetPath()) if bound else None)
clone_validation = []
for index, source_prim in enumerate(mesh_prims):
    source_mesh = UsdGeom.Mesh(source_prim)
    source_points = list(source_mesh.GetPointsAttr().Get() or [])
    counts = list(source_mesh.GetFaceVertexCountsAttr().Get() or [])
    indices = list(source_mesh.GetFaceVertexIndicesAttr().Get() or [])
    source_world = xforms.GetLocalToWorldTransform(source_prim)
    world_points = [
        Gf.Vec3f(source_world.Transform(Gf.Vec3d(float(p[0]), float(p[1]), float(p[2]))))
        for p in source_points
    ]
    clone = UsdGeom.Mesh.Define(stage, f"/__PhysXDiagnostic/CloneMesh_{index}")
    clone.CreatePointsAttr(world_points)
    clone.CreateFaceVertexCountsAttr(counts)
    clone.CreateFaceVertexIndicesAttr(indices)
    clone.CreateOrientationAttr(UsdGeom.Tokens.rightHanded)
    clone.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    clone.CreateDoubleSidedAttr(True)
    clone.CreateVisibilityAttr(UsdGeom.Tokens.inherited)
    clone.CreateDisplayColorPrimvar(UsdGeom.Tokens.constant).Set([Gf.Vec3f(0.15, 0.65, 0.95)])
    clone.CreateDisplayOpacityPrimvar(UsdGeom.Tokens.constant).Set([1.0])
    UsdShade.MaterialBindingAPI.Apply(clone.GetPrim()).Bind(diagnostic_material)
    relation = clone.GetPrim().GetRelationship("material:binding")
    computed = UsdShade.MaterialBindingAPI(clone.GetPrim()).ComputeBoundMaterial()[0]
    clone_validation.append(
        {
            "path": str(clone.GetPath()),
            "points": len(world_points),
            "faces": len(counts),
            "triangles": sum(max(0, int(n) - 2) for n in counts),
            "world_bounds": bounds(world_points),
            "double_sided": bool(clone.GetDoubleSidedAttr().Get()),
            "visibility": str(UsdGeom.Imageable(clone.GetPrim()).ComputeVisibility()),
            "direct_material_binding_targets": [str(x) for x in relation.GetTargets()],
            "computed_material": str(computed.GetPath()) if computed else None,
        }
    )
reference_cube = UsdGeom.Cube.Define(stage, "/__PhysXDiagnostic/ReferenceCube")
reference_cube.CreateSizeAttr(0.35)
reference_cube.AddTranslateOp().Set(Gf.Vec3d(1.8, 0.2, 0.15))
reference_cube.CreateDisplayColorPrimvar(UsdGeom.Tokens.constant).Set([Gf.Vec3f(1.0, 0.3, 0.08)])
stage.SetEditTarget(original_target)

settings = carb.settings.get_settings()
result = {
    "status": "PASS_STATIC_AUDIT",
    "input_usd": {"path": str(INPUT_USD), "bytes": INPUT_USD.stat().st_size, "sha256": actual_sha},
    "physics_variant": root.GetVariantSet("Physics").GetVariantSelection(),
    "mesh_count": len(rows),
    "meshes": rows,
    "solid_diagnostic_static_validation": {
        "session_layer_only": True,
        "material": str(diagnostic_material.GetPath()),
        "resolved_on_meshes": diagnostic_bound_paths,
        "all_meshes_resolve_diagnostic_material": all(
            path == str(diagnostic_material.GetPath()) for path in diagnostic_bound_paths
        ),
        "source_usd_modified": False,
    },
    "clone_diagnostic_static_validation": {
        "session_layer_only": True,
        "clone_meshes": clone_validation,
        "reference_cube": str(reference_cube.GetPath()),
        "all_clones_have_direct_binding": all(
            row["direct_material_binding_targets"] == [str(diagnostic_material.GetPath())]
            for row in clone_validation
        ),
        "all_clones_resolve_material": all(
            row["computed_material"] == str(diagnostic_material.GetPath()) for row in clone_validation
        ),
        "source_usd_modified": False,
    },
    "viewport_persistent_mesh_visibility": settings.get(
        "/persistent/app/viewport/Viewport/Viewport0/scene/meshes/visible"
    ),
    "renderer_enabled": settings.get("/renderer/enabled"),
    "physics_steps": 0,
}
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print("PHYSX_STATIC_MESH_AUDIT=" + json.dumps({"status": result["status"], "mesh_count": len(rows)}))
omni.kit.app.get_app().post_quit(0)
