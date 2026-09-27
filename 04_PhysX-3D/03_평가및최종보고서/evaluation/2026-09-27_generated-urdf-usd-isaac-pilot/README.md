# Generated-output URDF → USD → Isaac Sim pilot: readiness contract

## Decision

**Blocked before URDF/USD generation.**  The official converter cannot be
applied to generated output directly, and using its available inputs would
copy GT kinematics into the purported generated asset.  No URDF, USD, Isaac
Sim asset, or joint-motion smoke test was produced.

`urdf_gen.py` is GT-only: it sets `jsonpath=finaljson` and
`geopath=partseg` (lines 31–44), reads `jsondata['group_info']` (line 44), and
uses original per-part OBJ paths (lines 58–61 and 94–102).  For B joints it
reads the GT direction and limits from `mov[...]` (lines 131–142); for C it
reads GT axis, point, and limits (lines 144–160), including the GT parent
selection at lines 109–116.  It has no generated-mesh/property input option.

| Contract field | Classification | Evidence / decision |
| --- | --- | --- |
| Generated mesh path, vertices, faces | `official_generated` | Existing `mesh.obj` for 24566 and 29806 is hash-verified by their decoder runs. |
| Scale scalar | `official_generated` | Existing property/audit result has the model output expression; its physical unit conversion is not established for URDF. |
| Vertex group IDs / group count | `official_generated` | Existing official-result audits expose group diagnostics, but not separate watertight per-link collision meshes. |
| Joint parent/type/axis/origin/range | `missing` | Generated-output schema does not establish a validated URDF mapping.  The official converter obtains these from GT `group_info`; that path is prohibited here. |
| Segmented visual/collision links | `proposed_conversion` | Would require a documented generated-mesh face/vertex segmentation and link mesh generation; none is an official generated-output converter. |
| Mass, density, inertia | `missing` | No verified generated-output-to-URDF mass/inertia contract or unit convention. |
| Collision mesh policy | `missing` | No official generated-output collision decomposition policy. |
| Isaac Sim runtime | `missing` | No `isaac-sim.sh`, selector, or installed runtime was found in the read-only checked PHYSx/home locations. |

24566 remains a generated group false negative: its official predicted group
count is one despite GT's drawer group.  It supplies no generated moving link,
so generated-only articulated URDF is blocked.  29806 remains underpredicted:
its GT has four groups while prior generated probes had two or three; a group
diagnostic is not a validated parent/type/axis/origin/range contract.  Neither
case may be repaired with GT JSON fields.

The minimum future *proposed* mapping, to be validated independently before
any simulation, is: (1) deterministic conversion of generated vertex groups
to disjoint visual/collision link meshes; (2) explicit generated kinematic
head decoding with units and coordinate frame; (3) a generated density/mass
and inertia convention; (4) URDF import settings; and (5) a locally installed
headless Isaac Sim version.  Such a proposed conversion would be distinct from
the official GT `urdf_gen.py` pipeline and from paper Table 2 evaluation.
