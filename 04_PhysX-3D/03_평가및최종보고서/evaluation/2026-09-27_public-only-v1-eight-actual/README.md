# Public-only v1: eight actual artifacts

This is an independent public-materials evaluation condition, **not** a
PhysX-3D Table 2 reproduction. Eight of the official 1,000 test rows have
artifact-complete outputs. `eight_sample_report.json` keeps raw-coordinate and
canonical-shape geometry separate, records deterministic sampling, and
excludes 23787/27281 from numeric denominators while retaining them in
`failure_ledger.json`.

Geometry uses 8,192 area-weighted barycentric PCG64 surface samples per mesh
with seed `20260927`. Symmetric CD-L1 is the sum of directional mean Euclidean
nearest-neighbour distances; CD-L2 uses squared distances in the same form.
F-score is the harmonic mean of directional hit fractions at Euclidean 0.05.
The canonical condition independently centers each mesh at its bounding-box
center and divides it by its own maximum bounding-box extent. Raw and
canonical scores are not averaged or mixed.

The report preserves source test row and duplicate-occurrence metadata,
per-artifact SHA256 data, group vertex/face/area/component diagnostics, and
separate overall plus fixed/B-translation/C-rotation summaries. Appearance,
density/affordance, description, and NAP/Paper aggregation remain blocked:
the public material lacks the paired maps/masks, official camera and range
rules, question/part correspondence, PhysX-to-NAP conversion, and benchmark
denominator/configuration rules.

To extend to 10–30 samples, first freeze an eligible manifest, validate source
and ShapeNet texture members, render conditioning, then use the measured
sampling latent gate before any decoder. The current census identifies missing
ShapeNet category archives and still leaves the paper evaluator inputs
unavailable.
