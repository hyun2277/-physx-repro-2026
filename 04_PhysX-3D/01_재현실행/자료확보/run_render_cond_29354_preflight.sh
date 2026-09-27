#!/usr/bin/env bash
set -u
ROOT=/home/minsujo/Desktop/SH/PHYSx
SRC="$ROOT/sources/physx-4f54e750a309"
PY="$ROOT/envs/physxgen/bin/python"
MODEL="$ROOT/staging/retrieval-29354-20260925T183908Z/phy_dataset/29354/model_tex.obj"
EXPECTED_MODEL_SHA=e58a15b42169119b66da9db751e25ed00c0c57d41de3db83d022538617532633
EXPECTED_HEAD=4f54e750a309fe9cd9f20816916ecc0e8a9ae594
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
STAGE="$ROOT/staging/render-cond-29354-$RUN_ID"
LOG="$ROOT/logs/render-cond-29354/$RUN_ID"
mkdir -p "$STAGE/phy_dataset/29354" "$STAGE/datasets/PhysXNet/renders_cond/29354_" "$LOG"
cp "$MODEL" "$STAGE/phy_dataset/29354/model_tex.obj"
MODEL_COPY="$STAGE/phy_dataset/29354/model_tex.obj"
"$PY" - "$STAGE/datasets/PhysXNet/metadata.csv" "$MODEL_COPY" <<'PY'
import csv, pathlib, sys
out, model = map(pathlib.Path, sys.argv[1:])
fields=['sha256','file_identifier','aesthetic_score','captions','rendered','voxelized','num_voxels','cond_rendered','local_path']
with out.open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerow({'sha256':'29354_','file_identifier':'0','aesthetic_score':'10','captions':'0','rendered':'False','voxelized':'False','num_voxels':'0','cond_rendered':'False','local_path':str(model)})
PY
{
 echo "run_id=$RUN_ID"; echo "started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"; echo "source=$SRC"; echo "source_head=$(git -C "$SRC" rev-parse HEAD)"; echo "stage=$STAGE"; echo "log=$LOG"
 echo "render_cond_sha=$(sha256sum "$SRC/dataset_toolkits/render_cond.py" | awk '{print $1}')"
 echo "blender_script_sha=$(sha256sum "$SRC/dataset_toolkits/blender_script/render.py" | awk '{print $1}')"
 echo "model_original_sha=$(sha256sum "$MODEL" | awk '{print $1}')"; echo "model_copy_sha=$(sha256sum "$MODEL_COPY" | awk '{print $1}')"
 echo 'metadata_csv_sha='$(sha256sum "$STAGE/datasets/PhysXNet/metadata.csv" | awk '{print $1}')
 echo 'tracked_status_begin'; git -C "$SRC" status --short; echo 'tracked_status_end'
 "$PY" -c 'import pandas,numpy,easydict; print("python_imports=pass",pandas.__version__,numpy.__version__)'
 echo "blender_path=/tmp/blender-3.0.1-linux-x64/blender"
 if test -x /tmp/blender-3.0.1-linux-x64/blender; then echo blender_present=true; else echo blender_present=false; fi
 echo 'official_missing_blender_actions= sudo apt-get update; sudo apt-get install -y libxrender1 libxi6 libxkbcommon-x11-0 libsm6; wget Blender3.0.1; tar -xvf'
 echo "intended_command=$PY $SRC/dataset_toolkits/render_cond.py PhysXNet --output_dir $STAGE/datasets/PhysXNet --instances 29354_ --num_views 24 --max_workers 1"
 find "$STAGE" -type f -printf '%P %s bytes\n' | sort
} > "$LOG/preflight.log" 2>&1

if ! grep -q 'source_head='$EXPECTED_HEAD "$LOG/preflight.log"; then echo 'ABORT_REASON: source HEAD mismatch' > "$LOG/abort_reason.txt"; echo 2 > "$LOG/exit_code.txt"; exit 2; fi
if test "$(sha256sum "$MODEL" | awk '{print $1}')" != "$EXPECTED_MODEL_SHA"; then echo 'ABORT_REASON: model_tex hash mismatch' > "$LOG/abort_reason.txt"; echo 2 > "$LOG/exit_code.txt"; exit 2; fi
if ! grep -q 'blender_present=false' "$LOG/preflight.log"; then echo 'ABORT_REASON: unexpected Blender state' > "$LOG/abort_reason.txt"; echo 2 > "$LOG/exit_code.txt"; exit 2; fi
echo 'ABORT_REASON: official render_cond requires missing Blender 3.0.1; apt/sudo/download prohibited' > "$LOG/abort_reason.txt"
echo '2' > "$LOG/exit_code.txt"
echo "ended_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG/preflight.log"
exit 2
