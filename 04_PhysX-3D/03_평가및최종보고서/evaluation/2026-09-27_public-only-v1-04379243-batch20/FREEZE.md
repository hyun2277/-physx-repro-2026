# Public-only v1: 20-artifact freeze

**Frozen result commit:** `f3587b9069abac5a5b6a7dd02d3789412d3bf036`  
**Frozen scope:** public-materials independent evaluation v1; **not** a
paper-equivalent Table 2 evaluation.

The referenced result set has 20 artifact-complete and metric-successful
samples.  Its class distribution is fixed=15, B-translation=3, and
C-rotation=2.  The aggregate has no metric-failed sample in its denominator;
it retains 120 blocked metric rows for the unavailable evaluation areas.

The frozen failure/exclusion ledger is: 23787 failed because the official
retrieval output OBJ was non-finite; 14567 failed because its ShapeNet MTL had
no `map_Kd` texture; 27370 failed because its official retrieval output
`model_tex.obj` was non-finite; and 27281 remains excluded after mesh-decoder
OOM under the unchanged 28,000 MiB hard limit and 4,607 MiB reserve.  Two
remaining batch candidates (26121 and 18778) were not started once the
20-artifact target was reached.

This record references existing artifacts only.  No mesh, model, data, image,
latent, cache, or run log is copied here.  Their integrity references are the
following existing files and SHA256 values:

| Existing file | SHA256 |
| --- | --- |
| `README.md` | `c41b25c6e1529d4de3bffd127a850a26cc59cc80339de8eb2c0bb7f133cc44c4` |
| `selection_manifest.json` | `21459f739bd33087c5b2404aa1169f6eedcb73f536021d580e660a79def0df37` |
| `batch_summary.json` | `8ae83fdad9dd3769afdf39c7994462dfbe3a3faa9be730c3f82afdc314ccf803` |
| `eight_sample_report.json` | `6ac4546528013667182ffb95dbf2c8aee519235380e8b64ef30cdf9da1d517a4` |
| `metric_audit.json` | `ae622b2b97658dbae0a6b2375ed13639dec512dda3a0455a288f7ace56849249` |
| `failure_ledger.json` | `4b10a0c962de366dec9fc3da8d93cbc8e46462587a0d905de950dde39d89b1b2` |
| `records.csv` | `250efc789ee7456f659d3cf0023f3a8ce3203246029108e861effaba9e00d01c` |
| `results.json` | `376faeb9fc6f56cedc4b6d794d51f26ec851b2cc3ff911faf8c66d182cf36774` |

The scope remains limited because the public release does not establish the
paper's full test conditioning manifest, 30-view camera/mask protocol,
paired GT maps and correspondence, description question mapping, NAP
conversion, or Table 2 duplicate/failure aggregation convention.
