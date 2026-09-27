# Public-only v1 articulation balance extension

This independent public-materials extension is not a paper Table 2
reproduction.  It reused the frozen GPU-1 seed-1 native adapter, 28,000 MiB
limit, and 4,607 MiB reserve without changing evaluator or adapter math.

Both pre-existing archives verified against official metadata: `02933112.zip`
is 432,747,631 bytes with SHA256
`f36bea3c118cb4818e751c8a6bdc8fd9202ed0dca5ce873251b068bc9b5dc5cd`;
`03636649.zip` is 745,318,964 bytes with SHA256
`1ad7f8dc315d88cfd5bfdde7850e3b1880d88a15b2dd5ef2e16bfea86888adbb`.

Successful additions are B: 45443, 45645; C: 15896, 13737, 16693.  This
brings the aggregate to fixed=15, B=5, C=5 (25 total artifact-complete
samples).  15714 and 13348 were preflight-rejected because their MTLs lack
`map_Kd`; no extraction or inference was attempted for them.  Existing failure
ledger entries were retained.  The copied JSON/CSV files are CPU-only results
from the unchanged v1 evaluator; large artifacts are referenced only by their
existing run records.
