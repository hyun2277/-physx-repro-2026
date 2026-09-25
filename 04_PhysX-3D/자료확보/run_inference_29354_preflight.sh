#!/usr/bin/env bash
set -u
ROOT=/home/minsujo/Desktop/SH/PHYSx
SRC="$ROOT/sources/physx-4f54e750a309"
RENDER="$ROOT/staging/render-cond-29354-portable-20260925T185825Z/datasets/PhysXNet/renders_cond/29354_"
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$ROOT/logs/inference-29354/$RUN_ID"
mkdir -p "$LOG"
{
  echo "run_id=$RUN_ID"
  echo "source_head=$(git -C "$SRC" rev-parse HEAD)"
  echo "transforms=$RENDER/transforms.json"
  sha256sum "$RENDER/transforms.json"
  echo "tracked_diff_begin"
  git -C "$SRC" diff --name-status
  echo "tracked_diff_end"
  echo "untracked_begin"
  git -C "$SRC" status --short --untracked-files=all | awk '$1=="??" {print}'
  echo "untracked_end"
} > "$LOG/preflight.log" 2>&1

"$ROOT/envs/physxgen/bin/python" -B - "$RENDER" "$LOG/selection.log" <<'PY'
import hashlib, json, math, pathlib, sys
from PIL import Image
render, log = map(pathlib.Path, sys.argv[1:])
data = json.loads((render / 'transforms.json').read_text())
frames = data.get('frames', [])
if len(frames) != 24:
    raise SystemExit(f'expected 24 frames, got {len(frames)}')
valid = []
for i, frame in enumerate(frames):
    rel = frame['file_path']; image = (render / rel).resolve()
    matrix = frame['transform_matrix']
    if len(matrix) != 4 or any(len(row) != 4 for row in matrix):
        raise SystemExit(f'bad matrix shape at frame {i}')
    if not all(math.isfinite(float(v)) for row in matrix for v in row):
        raise SystemExit(f'nonfinite matrix at frame {i}')
    if not image.is_file():
        raise SystemExit(f'missing image {image}')
    valid.append((i, rel, image, matrix))
i, rel, image, matrix = valid[0]
with Image.open(image) as im:
    im.load()
with image.open('rb') as f:
    image_hash = hashlib.sha256(f.read()).hexdigest()
with open(log, 'w') as out:
    out.write(f'validated_frames={len(valid)}\nselected_index={i}\nselected_file={rel}\n')
    out.write(f'selected_path={image}\nselected_png_sha256={image_hash}\n')
    out.write('selected_transform=' + json.dumps(matrix, separators=(',', ':')) + '\n')
PY

if test -n "$(git -C "$SRC" diff --name-only)"; then
  echo 'ABORT_REASON=tracked source changes present; example.py was not executed' | tee "$LOG/abort_reason.txt"
  echo 2 > "$LOG/exit_code.txt"
  exit 2
fi
echo 'ABORT_REASON=preflight only; no execution requested because source diff gate failed' > "$LOG/abort_reason.txt"
echo 2 > "$LOG/exit_code.txt"
exit 2
