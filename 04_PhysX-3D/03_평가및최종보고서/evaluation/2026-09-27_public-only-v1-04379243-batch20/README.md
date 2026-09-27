# 04379243 batch expansion: 20 artifact-complete samples

This is a **public-materials independent evaluation v1** expansion.  It is not
the paper's Table 2 evaluation and must not be compared numerically with it.

The batch selected twelve `NEEDS_CONDITIONING` rows whose existing eligibility
audit recorded a 04379243 ShapeNet OBJ, MTL, and referenced texture, along with
two-part PhysXNet source geometry.  No new archive was downloaded and no
archive was fully extracted.  The first nine new artifact-complete samples were
`19661`, `25862`, `31114`, `22738`, `24163`, `27499`, `25598`, `19335`, and
`34676`; with the frozen baseline eleven, this reaches twenty.  `27370` failed
the existing retrieval verifier because the official `model_tex.obj` contained
non-finite data.  It was not retried.  `26121` and `18778` were intentionally
not started once the target was reached.

No eligible B-translation or C-rotation row remained in the currently
available 04379243 `NEEDS_CONDITIONING` set after retaining the pre-existing
27281 and 23787 exclusions.  The nine additions are fixed samples; the twenty
sample totals therefore contain fixed=15, B-translation=3, and C-rotation=2.

The unchanged runner used GPU 1, `SPCONV_ALGO=native`, seed 1, the existing
CUDA 12.8/GCC 12 overlay, mandatory small adapter equivalence checks, a 28,000
MiB hard limit, and a 4,607 MiB reserve.  Each sample used independent
timestamped extraction, rendering, sampling, and split physics/mesh decoder
children.  The evaluator was reused without changes; raw and independently
canonicalized geometry measures remain separate.

`eight_sample_report.json` is retained under its historical evaluator filename
but contains all twenty successful records.  It specifies deterministic
area-weighted 8,192-point surface sampling (seed 20260927), symmetric CD L1/L2,
and F-score at threshold 0.05.  Appearance, density/affordance PSNR,
description, NAP COV/MMD, and paper-equivalent aggregation remain blocked by
the previously recorded missing paired maps/masks, cameras, correspondence,
and aggregation conventions.
