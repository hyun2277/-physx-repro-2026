# PhysX-Bench compatibility audit for PhysX-3D public-only v1 (25 artifacts)

This is a readiness audit for a later benchmark.  It is neither PhysX-3D Table
2 reproduction nor a cross-paper score comparison.

## Source and smoke test

The official `physx-omni/PhysX-Omni` repository was cloned separately at
`/home/minsujo/Desktop/SH/PHYSx/sources/physx-omni-benchmark`, commit
`46fa1cd0b6883d4d14431d51c3326ef80a85ef64`.  Its
`benchmark/scripts/run_tiny_smoke_test.sh` passed without a VLM, GPU, model
download, Blender, MuJoCo, or simulation.  It verified RQS manifest building,
aggregation, and strict denominator validation using its synthetic 1×1 PNG.

## Artifact compatibility counts (25 public-only v1 artifacts)

| Metric | READY | DERIVABLE_WITH_EXPLICIT_CONVERSION | MISSING | INVALID | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| RQS | 0 | 0 | 25 | 0 | No benchmark 30-view rendered evidence or quality reference. |
| MCS | 0 | 0 | 25 | 0 | No benchmark rendered view set. |
| DQS | 0 | 25 | 0 | 0 | Existing conditioning `000.png` and generated scale expression exist; export to benchmark `scale.npy`/equivalent is a proposed conversion, not an official PhysXGen output file. |
| APS | 0 | 0 | 25 | 0 | No affordance heatmap views/masks. |
| DCS | 0 | 0 | 25 | 0 | No same-view color render, binary part mask, or benchmark reference description. |
| KPS | 0 | 0 | 25 | 0 | No generated-only URDF or standardized articulation video; GT JSON is prohibited. |
| MPS | 0 | 0 | 25 | 0 | No generated material parameter contract, watertight conversion, water/floor evidence. |

`DERIVABLE_WITH_EXPLICIT_CONVERSION` is deliberately not READY: DQS requires a
new documented export of the existing generated scale scalar, with units and
benchmark filename mapping frozen before any score.  It must not use GT scale
or change current artifacts.

The full PhysX-Bench environment additionally lists Python 3.11, Pillow,
NumPy, PyYAML, image libraries, trimesh/Open3D, PyTorch, and optional VLM,
Blender, MuJoCo, and Genesis layers.  No dependency was installed here.  The
tiny smoke needed only existing Python standard-library functionality.
