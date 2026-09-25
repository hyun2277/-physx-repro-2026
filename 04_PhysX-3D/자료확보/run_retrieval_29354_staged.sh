#!/usr/bin/env bash
set -u

ROOT=/home/minsujo/Desktop/SH/PHYSx
SRC="$ROOT/sources/physx-4f54e750a309"
MERGE_STAGE="$ROOT/staging/merge-29354-20260925T180423Z/phy_dataset/29354/model.obj"
SHAPE="$ROOT/data/shapenetcore/minimal/29354"
PY="$ROOT/envs/physxgen/bin/python"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
STAGE="$ROOT/staging/retrieval-29354-$RUN_ID"
LOG="$ROOT/logs/retrieval-29354/$RUN_ID"
mkdir -p "$STAGE/phy_dataset/29354" "$STAGE/shapenet/04379243/db406d9b2a94bce5622d7484764b58f/models" "$STAGE/shapenet/04379243/db406d9b2a94bce5622d7484764b58f/images" "$LOG"

cp "$MERGE_STAGE" "$STAGE/phy_dataset/29354/model.obj"
cp "$SHAPE/models/model_normalized.obj" "$STAGE/shapenet/04379243/db406d9b2a94bce5622d7484764b58f/models/"
cp "$SHAPE/models/model_normalized.mtl" "$STAGE/shapenet/04379243/db406d9b2a94bce5622d7484764b58f/models/"
cp "$SHAPE/images/texture0.jpg" "$STAGE/shapenet/04379243/db406d9b2a94bce5622d7484764b58f/images/"

# Restrict finalindex.json to the single verified sample after comparing the fixed source.
"$PY" - "$SRC/tools/finalindex.json" "$STAGE/finalindex.json" <<'PY'
import json, pathlib, sys
src, dst = map(pathlib.Path, sys.argv[1:])
d = json.loads(src.read_text())
expected = 'shapenet/04379243/db406d9b2a94bce5622d7484764b58f'
if d.get('29354') != expected:
    raise SystemExit(f'finalindex mismatch: {d.get("29354")!r}')
dst.write_text(json.dumps({'29354': d['29354']}, indent=2) + '\n')
PY

{
  echo "run_id=$RUN_ID"
  echo "source=$SRC"
  git -C "$SRC" rev-parse HEAD 2>/dev/null || true
  echo "stage=$STAGE"
  echo "log=$LOG"
  echo "model_source=$MERGE_STAGE"
  sha256sum "$MERGE_STAGE"
  sha256sum "$STAGE/finalindex.json" "$STAGE/shapenet/04379243/db406d9b2a94bce5622d7484764b58f/models/model_normalized.obj" "$STAGE/shapenet/04379243/db406d9b2a94bce5622d7484764b58f/models/model_normalized.mtl" "$STAGE/shapenet/04379243/db406d9b2a94bce5622d7484764b58f/images/texture0.jpg"
  "$PY" -c 'import trimesh, PIL; print("imports=ok", trimesh.__version__, PIL.__version__)'
  echo "CUDA_VISIBLE_DEVICES=''"
  echo "command=$PY $SRC/dataset_toolkits/retrieval_texture_example.py --index 0 --range 1"
  find "$STAGE/phy_dataset" "$STAGE/shapenet" -type f -printf '%P %s bytes\n' | sort
} > "$LOG/preflight.log" 2>&1

if ! PYTHONDONTWRITEBYTECODE=1 "$PY" -c 'import trimesh, PIL' >> "$LOG/preflight.log" 2>&1; then
  echo "ABORT_REASON: required Python import missing" | tee "$LOG/abort_reason.txt"
  exit 2
fi

set +e
(
  cd "$STAGE" || exit 10
  CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 "$PY" "$SRC/dataset_toolkits/retrieval_texture_example.py" --index 0 --range 1
) > "$LOG/stdout.log" 2> "$LOG/stderr.log"
RC=$?
set -e
echo "$RC" > "$LOG/exit_code.txt"

if test "$RC" -eq 0; then
  "$PY" - "$STAGE" > "$LOG/output_verification.log" 2>&1 <<'PY'
from pathlib import Path
import hashlib, sys
root=Path(sys.argv[1])/'phy_dataset/29354'
out=root/'model_tex.obj'
if not out.is_file(): raise SystemExit(f'missing {out}')
def sha(p):
 h=hashlib.sha256(); h.update(p.read_bytes()); return h.hexdigest()
print(f'{out} {out.stat().st_size} sha256={sha(out)}')
text=out.read_text(errors='replace').splitlines()
mtl=[x.split(maxsplit=1)[1].strip() for x in text if x.startswith('mtllib ')]
print('mtllib=',mtl)
if len(mtl)!=1: raise SystemExit('expected exactly one mtllib reference')
mtl_path=(out.parent/mtl[0]).resolve()
if not mtl_path.is_file(): raise SystemExit(f'missing referenced mtl {mtl_path}')
print(f'{mtl_path} {mtl_path.stat().st_size} sha256={sha(mtl_path)}')
refs=[]
for line in mtl_path.read_text(errors='replace').splitlines():
 if line.startswith('map_Kd '): refs.append(line.split(maxsplit=1)[1].strip())
print('map_Kd=',refs)
for ref in refs:
 p=(mtl_path.parent/ref).resolve()
 if not p.is_file(): raise SystemExit(f'missing referenced texture {p}')
 print(f'{p} {p.stat().st_size} sha256={sha(p)}')
PY
  VERIFY_RC=$?
  echo "$VERIFY_RC" > "$LOG/output_verification_exit_code.txt"
else
  echo "retrieval_failed; no retry performed" > "$LOG/output_verification.log"
fi
exit "$RC"
