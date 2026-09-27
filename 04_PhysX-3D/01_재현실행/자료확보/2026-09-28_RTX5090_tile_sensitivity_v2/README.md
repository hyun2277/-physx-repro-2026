# RTX 5090 adapter tile sensitivity

This is an adapter sensitivity probe, not a CUDA 11.8 comparison, a complete adapter-equivalence proof, or a PhysX-3D Table 2 reproduction.

## Fixed conditions

- Same saved conditioning `000.png`, checkpoints, seed 1, GPU 1, Native spconv, CUDA 12.8.1 overlay, GCC 12, output-channel tiling, streaming GroupNorm, and separated physics/mesh decoder children.
- GPU monitor limit: 28,000 MiB; reserve: 4,607 MiB. Each physics and mesh child passed its proactive pre-allocation guard.
- Configurations: baseline A = 256 input channels/tile; baseline B = independent 256 control; comparison = 128 input channels/tile.
- Sampling itself shows CUDA repeat variation despite the same seed. Mesh topology can therefore differ and raw vertex rows are not compared after a vertex-count mismatch. Deterministic surface diagnostics, scale, and group diagnostics are retained separately.

## Results

| Object | 256 control vs baseline | 128 vs baseline | Native input tiling trace | Judgment |
|---|---:|---:|---|---|
| 29354 | phy latent rel-L2 0.00123175 | phy latent rel-L2 0.00121284 | 256/128 observed | `numerically_different_but_semantically_stable` |
| 29806 | phy latent rel-L2 0.0046642 | phy latent rel-L2 0.00606931 | not invoked for this input | `numerically_different_but_semantically_stable` |

## Semantic screen

### 29354

- Official group count: 256 = 2; 128 = 2.
- Moving-group meaningful screen: 256 = {'1': False}; 128 = {'1': False}.
- Predicted scale mean [cm]: 256 = 99.789146; 128 = 98.747597.
### 29806

- Official group count: 256 = 2; 128 = 2.
- Moving-group meaningful screen: 256 = {'1': True}; 128 = {'1': True}.
- Predicted scale mean [cm]: 256 = 105.04199; 128 = 105.049.
- baseline_a group 1: area=0.31531888246536255, area_fraction=0.12471488863229752, components=126.
- baseline_b_control group 1: area=0.31652361154556274, area_fraction=0.12519904971122742, components=124.
- tile_128 group 1: area=0.31046968698501587, area_fraction=0.12280477583408356, components=120.

`numerically_different_but_semantically_stable` means that the declared group-count and meaningful-moving-surface screen matched while floating-point/mesh outputs differed. It does not establish bitwise equality, full adapter fidelity, physical accuracy, or paper-level evaluation equivalence.

The full small comparison record is `sensitivity_result.json`; all referenced large artifacts remain outside Git.
