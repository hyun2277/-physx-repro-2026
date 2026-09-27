# Public-only v1 extension execution

This is a proposed public-materials independent evaluation condition, not a reproduction of PhysX-3D Table 2 or its official evaluation. It reuses the existing 29354/24566/29806 results and adds five generated artifacts. 23787 remains a recorded failure: its official texture-retrieval output failed the finite-OBJ verifier, so it was not retried or treated as a zero score.

`results.json`, `records.csv`, and `manifest.json` contain CPU-computed geometry, scalar scale, and group-surface diagnostics for the eight artifact-complete samples. Appearance, density, affordance, description, parent/axis/range accuracy, 30-view evaluation, and paper-level aggregation remain blocked under the v1 protocol.

## Selection and execution status

The extension selected **21356, 27703, 30719, 21314, 32980** (fixed) and
**23787** (C rotation). All six had directly verified JSON/part-OBJ material
in the existing PhysXNet ZIP and OBJ/MTL/referenced-texture members in the
existing ShapeNetCore `04379243.zip`. There was no additional safe B
translation candidate: 27281 is the only B-containing `NEEDS_CONDITIONING`
candidate in the prior manifest and is excluded by its already observed
73,024-row latent / mesh-decoder OOM evidence under the unchanged 28,000 MiB
hard limit and 4,607 MiB reserve.

The five fixed samples each passed the measured per-latent decoder gate and
completed separate physics and mesh decoder children. 23787 failed at the
official retrieval output verification because its generated `model_tex.obj`
contains non-finite OBJ data. It was neither retried nor converted to a
metric zero. `extension_execution_summary.json` preserves this failed row;
the batch's timestamped external logs retain all command, environment, GPU,
and child-output detail.

## Later archive candidates

The eligibility census keeps `48419` and `38882` behind ShapeNet category
`02933112.zip`, and `14567` and `15821` behind `03636649.zip`; their archive
sizes were not directly verified and remain `unknown`. No new archive was
downloaded in this run. PartNet is not required for this public-only path:
the required JSON and per-part OBJ inputs are already in PhysXNet, while the
texture linkage is supplied by ShapeNetCore. This does not establish that
PartNet is unnecessary for the paper's separate Table 2 protocol.
