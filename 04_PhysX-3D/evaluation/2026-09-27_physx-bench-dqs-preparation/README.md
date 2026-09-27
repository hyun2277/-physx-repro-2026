# PhysX-Bench DQS preparation (25 public-only v1 artifacts)

This prepares inputs only; it does not run a VLM or calculate DQS.

All 25 rows passed the official PhysX-Bench
`build_dimension_manifest.py` with `method=physxgen`, `dataset=mobility`, and
its expected `scale.npy` source.  Each row has one verified existing
conditioning `000.png` linked as `first_frame.png` and one separate staging
`scale.npy`.  Object IDs are unique; valid=25, excluded=0, duplicate=0, and
the ready denominator is 25.

Each `scale.npy` is a finite positive float64 scalar in cm.  It exports the
existing public-only v1 scale metric's official-audit expression, **predicted
vertex mean**, and does not modify an original artifact.  This is explicitly a
**proposed conversion** to the PhysX-Bench filename/schema; it is not an
official PhysXGen `scale.npy` output and should not be treated as such.

Official VLM status: **BLOCKED_BY_HARDWARE_OR_MODEL**.  The benchmark defaults
to `Qwen/Qwen3.5-122B-A10B` and loads BF16 weights via Transformers with
`device_map="auto"`; it does not configure tensor parallelism.  The official
model card states 122B total parameters.  BF16 weights alone require about
227 GiB (122e9 × 2 bytes), before runtime overhead; the two RTX 5090 GPUs
currently expose 32,607 MiB each (about 64 GiB total free capacity) and no
local 122B cache was found.  A quantized model or a different VLM would be a
nonofficial substitute, so it cannot establish an official DQS pilot.

Before VLM execution, the next required step is access to the official
unquantized model weights and a backend/hardware configuration with sufficient
aggregate memory for BF16 weights plus runtime overhead, while preserving the
official benchmark model and prompt path.
