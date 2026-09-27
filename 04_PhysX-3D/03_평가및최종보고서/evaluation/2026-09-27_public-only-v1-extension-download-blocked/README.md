# Public-only v1 extension: ShapeNet archive download blocked

This record concerns the proposed four-sample extension only. It does not
modify, retry, or remove any existing 8-sample artifact.

Official Hugging Face metadata was read with the existing approved ShapeNetCore
login. Disk space passed before transfer: 430,185,652,224 bytes free, versus
9,768,001,187 bytes reserved for the two archives plus 8 GiB staging margin.
The two requested files then failed safe resumable verification. Their retained
`.part` files exceed the official byte counts, and the checked `Range` response
for `03636649.zip` began at byte 620,756,992 instead of the requested local
offset. The downloader now rejects a resume response unless its content range
starts exactly at the retained byte count and has the official total size.

Both partial files and their PHYSx log records are preserved. They are not ZIP
inputs and are not extracted. Therefore 48419, 38882, 14567, and 15821 are
`download_blocked`; no merge, retrieval, Blender, GPU, inference, or metric
step was started for them. The public-only-v1 coverage remains 8 artifact
complete samples, not 12. This is not a paper Table 2 evaluation.
