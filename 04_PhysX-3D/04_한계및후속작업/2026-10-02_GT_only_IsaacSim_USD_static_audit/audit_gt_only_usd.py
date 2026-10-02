#!/usr/bin/env python3
"""Read-only audit of the existing GT-only URDF-to-USD conversion output.

This tool never invokes SimulationApp, URDFImporter, a GPU, or physics.  It
parses the already-written USDA layers, resolves the locally-authored Physics
variant payload paths, and reports USD schema/API tokens rather than prim
names.  It deliberately avoids the Kit runtime so this remains read-only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import re


CASES = ("10163", "29806", "29354")
GT_INPUTS = {
    "10163": "staging/articulated-sampling-10163-20260927T154942Z-fc8c4d6127dc/work/physxnet",
    "29806": "staging/articulated-sampling-29806-20260926T220010Z-ac2c1dfab94d/work/physxnet",
    "29354": "staging/merge-29354-20260925T180423Z/physxnet",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def text_attr(node: ET.Element | None, name: str) -> str | None:
    return None if node is None else node.get(name)


def audit_urdf(path: Path) -> dict:
    root = ET.parse(path).getroot()
    links = sorted(link.get("name") for link in root.findall("link"))
    joints = []
    for joint in root.findall("joint"):
        origin, axis, limit = joint.find("origin"), joint.find("axis"), joint.find("limit")
        joints.append(
            {
                "name": joint.get("name"),
                "type": joint.get("type"),
                "parent": text_attr(joint.find("parent"), "link"),
                "child": text_attr(joint.find("child"), "link"),
                "origin_xyz": text_attr(origin, "xyz"),
                "origin_rpy": text_attr(origin, "rpy"),
                "axis": text_attr(axis, "xyz"),
                "lower": text_attr(limit, "lower"),
                "upper": text_attr(limit, "upper"),
            }
        )
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path), "link_count": len(links), "links": links, "joint_count": len(joints), "joints": joints}


def audit_gt(root: Path, oid: str) -> dict:
    path = root / GT_INPUTS[oid] / "finaljson" / f"{oid}.json"
    data = json.loads(path.read_text())
    groups = data["group_info"]
    movable = []
    for group_id, value in groups.items():
        if group_id == "0":
            continue
        spec = value[-2]
        movable.append({
            "group": group_id,
            "parts": value[0],
            "parent_group": value[1],
            "type": value[-1],
            "axis": spec[:3],
            "origin": spec[3:6] if value[-1] in ("C", "D") else None,
            "range_raw": spec[-2:],
        })
    return {"path": str(path), "sha256": sha256(path), "group_count": len(groups), "fixed_parts": groups["0"], "movable_groups": movable}


PRIM_RE = re.compile(r'^\s*(?:(def)\s+([A-Za-z0-9_]+)\s+"([^"]+)"|(over)\s+"([^"]+)")')
API_RE = re.compile(r'apiSchemas\s*=\s*\[([^\]]*)\]', re.S)
PAYLOAD_RE = re.compile(r'(?:payload|references)\s*=\s*@([^@]+)@')
VARIANT_RE = re.compile(r'^\s*"([^"]+)"\s*\(\s*prepend payload\s*=\s*@([^@]+)@', re.M)


def layer_schema_items(path: Path) -> list[dict]:
    """Return every schema-bearing prim declaration in one USDA layer.

    This is a textual layer audit, not a guess from display names.  The joint
    schema is the exact USDA type token (for example PhysicsRevoluteJoint),
    and APIs are the exact authored apiSchemas tokens.
    """
    text = path.read_text(errors="replace")
    items: list[dict] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = PRIM_RE.match(line)
        if not match:
            continue
        definition, declared_type, defined_name, override, override_name = match.groups()
        kind = definition or override
        name = defined_name or override_name
        block = "\n".join(lines[index:min(index + 18, len(lines))])
        api_match = API_RE.search(block)
        apis = [] if api_match is None else re.findall(r'"([^"]+)"', api_match.group(1))
        items.append({"layer": str(path), "line": index + 1, "specifier": kind, "type_name": declared_type, "declared_type": declared_type, "name": name, "applied_schemas": apis})
    return items


def variant_payloads(root_usd: Path) -> dict[str, Path]:
    text = root_usd.read_text(errors="replace")
    out: dict[str, Path] = {}
    for name, target in VARIANT_RE.findall(text):
        out[name] = (root_usd.parent / target).resolve()
    return out


def layer_closure(seed_layers: list[Path], ignored_root_arcs: set[Path]) -> list[Path]:
    """Resolve only local USDA/USD arcs already written by the importer."""
    queue = list(seed_layers)
    seen: set[Path] = set()
    out: list[Path] = []
    while queue:
        layer = queue.pop(0).resolve()
        if layer in seen or not layer.exists():
            continue
        seen.add(layer); out.append(layer)
        for target in re.findall(r'@([^@]+\.(?:usd|usda))@', layer.read_text(errors="replace")):
            candidate = (layer.parent / target).resolve()
            if layer == seed_layers[0].resolve() and candidate in ignored_root_arcs:
                continue
            queue.append(candidate)
    return out


def audit_variant(root_usd: Path, variant: str | None) -> dict:
    payloads = variant_payloads(root_usd)
    layers = [root_usd]
    if variant is not None and variant in payloads:
        layers.append(payloads[variant])
    ignored = set(payloads.values())
    if variant is not None and variant in payloads:
        ignored.remove(payloads[variant])
    layers = layer_closure(layers, ignored)
    items = [item for layer in layers for item in layer_schema_items(layer)]
    data = {
        "selected_variant": variant if variant is not None else "none (no authored selection)",
        "layers_examined": [str(x) for x in layers],
        "prim_count": len(items),
        "revolute_joint_prims": [],
        "generic_joint_prims": [],
        "articulation_root_prims": [],
        "collision_prims": [],
        "rigid_body_prims": [],
        "prim_schemas": [],
    }
    for item in items:
        declared = item["declared_type"] or ""
        apis = item["applied_schemas"]
        identity = {key: item[key] for key in ("layer", "line", "specifier", "declared_type", "name")}
        if declared == "PhysicsRevoluteJoint":
            data["revolute_joint_prims"].append(identity)
        if declared.startswith("Physics") and declared.endswith("Joint"):
            data["generic_joint_prims"].append(identity)
        if "PhysicsArticulationRootAPI" in apis:
            data["articulation_root_prims"].append(identity)
        if "PhysicsCollisionAPI" in apis:
            data["collision_prims"].append(identity)
        if "PhysicsRigidBodyAPI" in apis:
            data["rigid_body_prims"].append(identity)
        if declared.startswith("Physics") or apis:
            data["prim_schemas"].append(item)
    for key in ("revolute_joint_prims", "generic_joint_prims", "articulation_root_prims", "collision_prims", "rigid_body_prims", "prim_schemas"):
        data[key].sort(key=lambda x: (x["layer"], x["line"], x["name"]))
    return data


def layer_arcs(root_usd: Path) -> dict:
    text = root_usd.read_text(errors="replace")
    payloads = variant_payloads(root_usd)
    default = re.search(r'defaultPrim\s*=\s*"([^"]+)"', text)
    reference_targets = PAYLOAD_RE.findall(text)
    return {
        "root_usd": str(root_usd),
        "root_sha256": sha256(root_usd),
        "default_prim": default.group(1) if default else None,
        "root_references_or_payloads": reference_targets,
        "variant_set": "Physics" if payloads else None,
        "variant_names": sorted(payloads),
        "authored_selection": None,
        "root_layer_sublayers": re.findall(r'@([^@]+\.usda)@', text),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"tool": "read-only USDA schema-token audit", "cases": {}}
    physx_root = args.staging.parent.parent
    rows = []
    for oid in CASES:
        urdf = args.staging / oid / f"gt_{oid}.urdf"
        root_usd = args.staging / oid / f"gt_{oid}" / f"gt_{oid}.usda"
        urdf_data = audit_urdf(urdf)
        gt_data = audit_gt(physx_root, oid)
        arcs = layer_arcs(root_usd)
        variants = [None] + arcs["variant_names"]
        usd_variants = {"authored_default": audit_variant(root_usd, None)}
        for variant in arcs["variant_names"]:
            usd_variants[variant] = audit_variant(root_usd, variant)
        report["cases"][oid] = {"gt": gt_data, "urdf": urdf_data, "usd_arcs": arcs, "usd_variants": usd_variants}
        for joint in urdf_data["joints"]:
            rows.append({"object_id": oid, **joint})
    (args.output / "audit_result.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    with (args.output / "urdf_joint_table.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["object_id", "name", "type", "parent", "child", "origin_xyz", "origin_rpy", "axis", "lower", "upper"])
        writer.writeheader(); writer.writerows(rows)
    print("GT_ONLY_USD_STATIC_AUDIT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
