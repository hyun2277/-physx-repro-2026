#!/usr/bin/env bash
set -u
ROOT=/home/minsujo/Desktop/SH/PHYSx
SRC="$ROOT/sources/physx-4f54e750a309"
PY="$ROOT/envs/physxgen/bin/python"
MODEL="$ROOT/staging/retrieval-29354-20260925T183908Z/phy_dataset/29354/model_tex.obj"
MODEL_SHA=e58a15b42169119b66da9db751e25ed00c0c57d41de3db83d022538617532633
BLENDER="$ROOT/tools/blender-3.0.1/unpacked/blender-3.0.1-linux-x64/blender"
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
STAGE="$ROOT/staging/render-cond-29354-portable-$RUN_ID"
LOG="$ROOT/logs/render-cond-29354-portable/$RUN_ID"
mkdir -p "$STAGE/phy_dataset/29354" "$STAGE/datasets/PhysXNet/renders_cond" "$LOG"
cp "$MODEL" "$STAGE/phy_dataset/29354/model_tex.obj"
"$PY" - "$STAGE/datasets/PhysXNet/metadata.csv" "$STAGE/phy_dataset/29354/model_tex.obj" <<'PY'
import csv, pathlib, sys
out,model=map(pathlib.Path,sys.argv[1:]); fields=['sha256','file_identifier','aesthetic_score','captions','rendered','voxelized','num_voxels','cond_rendered','local_path']
with out.open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerow({'sha256':'29354_','file_identifier':'0','aesthetic_score':'10','captions':'0','rendered':'False','voxelized':'False','num_voxels':'0','cond_rendered':'False','local_path':str(model)})
PY
{
 echo "run_id=$RUN_ID"; echo "started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"; echo "source_head=$(git -C "$SRC" rev-parse HEAD)"; echo "stage=$STAGE"; echo "blender=$BLENDER"; echo "blender_archive_sha256=$(sha256sum "$ROOT/tools/blender-3.0.1/blender-3.0.1-linux-x64.tar.xz" | awk '{print $1}')"; echo "model_sha256=$(sha256sum "$MODEL" | awk '{print $1}')"; echo "model_copy_sha256=$(sha256sum "$STAGE/phy_dataset/29354/model_tex.obj" | awk '{print $1}')"; "$BLENDER" --background --version; echo "command=CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 $PY $ROOT/repro-records/04_PhysX-3D/자료확보/render_cond_29354_portable.py --source-dir $SRC/dataset_toolkits --blender $BLENDER --model $STAGE/phy_dataset/29354/model_tex.obj --output $STAGE/datasets/PhysXNet --num-views 24"; } > "$LOG/preflight.log" 2>&1
if test "$(sha256sum "$MODEL" | awk '{print $1}')" != "$MODEL_SHA"; then echo 'ABORT_REASON: model hash mismatch' > "$LOG/abort_reason.txt"; echo 2 > "$LOG/exit_code.txt"; exit 2; fi
set +e
START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 "$PY" "$ROOT/repro-records/04_PhysX-3D/자료확보/render_cond_29354_portable.py" --source-dir "$SRC/dataset_toolkits" --blender "$BLENDER" --model "$STAGE/phy_dataset/29354/model_tex.obj" --output "$STAGE/datasets/PhysXNet" --num-views 24 > "$LOG/stdout.log" 2> "$LOG/stderr.log"
RC=$?
END=$(date -u +%Y-%m-%dT%H:%M:%SZ)
set -e
echo "start_utc=$START" >> "$LOG/command.log"; echo "end_utc=$END" >> "$LOG/command.log"; echo "$RC" > "$LOG/exit_code.txt"
if test "$RC" -ne 0; then echo 'ABORT_REASON: portable official _render_cond failed' > "$LOG/abort_reason.txt"; exit "$RC"; fi
"$PY" - "$STAGE/datasets/PhysXNet/renders_cond/29354_" > "$LOG/output_verification.log" 2>&1 <<'PY'
import json, math, pathlib, sys
from PIL import Image
import numpy as np
out=pathlib.Path(sys.argv[1]); t=out/'transforms.json'
if not t.is_file(): raise SystemExit('missing transforms.json')
d=json.loads(t.read_text()); frames=d.get('frames',[])
if not frames: raise SystemExit('no frames')
for i,f in enumerate(frames):
 p=(out/f['file_path']).resolve()
 if not p.is_file(): raise SystemExit(f'missing image {p}')
 with Image.open(p) as im: im.load(); print('image',i,p.name,im.format,im.size)
 m=np.asarray(f['transform_matrix'],dtype=float)
 if m.shape!=(4,4) or not np.isfinite(m).all(): raise SystemExit(f'bad matrix {i}')
print('frames',len(frames),'transforms=PASS','images=PASS','matrices=FINITE')
PY
VRC=$?
echo "$VRC" > "$LOG/output_verification_exit_code.txt"
if test "$VRC" -ne 0; then echo 'ABORT_REASON: output verification failed' >> "$LOG/output_verification.log"; exit "$VRC"; fi
exit 0
