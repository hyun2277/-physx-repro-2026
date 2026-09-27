# Density and affordance map readiness

This is a CPU-only public-materials audit, not PhysX-3D Table 2 or a paper-identical evaluation. The 11 artifact-complete samples retain their existing geometry/scale/group results, but **all 22 density/affordance map rows are blocked**. No PSNR, MAE, or RMSE was calculated from those samples.

The official preprocessing confirms density is read from the numeric prefix of a `g/cm^3` string and priority rank is an integer. Training normalizes rank as `1-rank/10` and density as `(density-2.3)/2.8`. The output head emits 14 channels without a semantic output activation; its normalized reading is grounded in that training loss. The example inverses density then min-max rescales display values per object, which is not a shared scoring range.

A metric-ready GT renderer is not established: the public GT script uses a stale `meshname` in the part loop and passes a `MeshExtractResult` to a helper that indexes `gt[0:3]`. There is also no official generated-mesh-to-GT-part correspondence, paired numeric maps/masks, fixed map value range, or scorer aggregation. Those are fail-closed prerequisites.

`camera_manifest.json` is a deterministic **candidate** based on the source Hammersley helper (`30`, `r=2`, `FOV=40`, `512`), stored for reproducibility only and not used for a score. `synthetic_validation.json` validates the proposed raw-unit intersection-map primitive and its rejection rules. Description PSNR and NAP COV/MMD remain blocked.
