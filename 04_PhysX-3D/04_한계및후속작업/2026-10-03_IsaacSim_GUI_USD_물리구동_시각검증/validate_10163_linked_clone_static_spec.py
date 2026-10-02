"""CPU-only checks for the linked-clone static GUI design."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
STAGING = Path("/home/minsujo/Desktop/SH/PHYSx/staging/gt-only-isaac-control-20261002T072614Z-gt-only-control/10163/gt_10163")
SPEC = json.loads((HERE / "10163_linked_clone_mapping_spec.json").read_text())
AUDIT = json.loads((HERE / "10163_composed_mesh_audit.json").read_text())


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    source = STAGING / "gt_10163.usda"
    physics = STAGING / "payloads/Physics/physics.usda"
    script = HERE / "gui_10163_linked_clone_static.py"
    assert sha256(source) == SPEC["source_usd_sha256"]
    text = physics.read_text()
    for value in (
        SPEC["gt_C_1"]["body0"],
        SPEC["gt_C_1"]["body1"],
        SPEC["fixed_component"]["body0"],
        SPEC["fixed_component"]["body1"],
        'token physics:axis = "X"',
        "float physics:lowerLimit = -90",
        "float physics:upperLimit = 90",
    ):
        assert value in text, value
    audit_rows = {row["path"]: row for row in AUDIT["meshes"]}
    for clone in SPEC["clones"]:
        row = audit_rows[clone["source_mesh"]]
        assert row["instance_proxy"] is True
        assert row["points_finite"] is True
        assert row["point_count"] == clone["source_point_count"]
        assert abs(row["linear_transform_determinant"] - 1.0) < 1.0e-12
    source_text = script.read_text()
    assert "SetInstanceable" not in source_text
    assert "from isaacsim.core.simulation_manager import" not in source_text
    assert "import warp as" not in source_text
    assert "SimulationManager.setup_simulation" not in source_text
    result = {
        "status": "PASS_CPU_STATIC_SPEC",
        "source_usd_sha256": SPEC["source_usd_sha256"],
        "clone_count": len(SPEC["clones"]),
        "physics_steps_requested": 0,
        "source_instance_deinstanced": False,
    }
    (HERE / "10163_linked_clone_static_spec_validation.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
