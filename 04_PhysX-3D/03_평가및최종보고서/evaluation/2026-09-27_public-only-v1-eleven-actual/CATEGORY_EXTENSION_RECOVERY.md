# ShapeNet category extension recovery

The two initially invalid partial files were preserved under `data/shapenetcore/raw/quarantine/20260927T111406Z-9dded638bbb1/`. Both exceeded the authenticated Hugging Face metadata size and failed SHA256 validation. That establishes corruption; it does not establish a server-side cause. A recorded direct HTTP Range response for `03636649` did not match the requested local offset, so the recovery uses a fresh authenticated client download with a unique temporary path and never resumes or appends either old partial.

Both replacement archives matched the authenticated `ShapeNet/ShapeNetCore` revision `73b692a98ee796df2f64511e0cbd4a8af2c20b27` byte-for-byte and by SHA256 before atomic promotion to `raw/<category>.zip`.

| Category | Expected and verified bytes | Verified SHA256 | Objects | Result |
|---|---:|---|---|---|
| 02933112 | 432,747,631 | `f36bea3c…b5dc5cd` | 48419, 38882 | both textured-source validation, pipeline, and public-only v1 metrics succeeded |
| 03636649 | 745,318,964 | `1ad7f8dc…88adbb` | 14567, 15821 | 15821 succeeded; 14567 stopped before retrieval/inference because its verified MTL has no `map_Kd` texture reference |

The three successes increase the artifact-complete public-only v1 set from eight to eleven. This remains an independent public-materials condition; it is neither Table 2 nor a paper-identical 1,000-test evaluation. The machine-readable ledger is [category_extension_recovery.json](category_extension_recovery.json).
