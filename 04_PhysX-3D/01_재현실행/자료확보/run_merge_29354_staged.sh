#!/usr/bin/env bash
set -u

ROOT=/home/minsujo/Desktop/SH/PHYSx
SRC="$ROOT/sources/physx-4f54e750a309"
INPUT="$ROOT/data/physxnet-minimal/2026-09-22/001-test-29354-fixed_candidate"
CLIP_CACHE="$ROOT/cache/clip"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
STAGE="$ROOT/staging/merge-29354-$RUN_ID"
LOG="$ROOT/logs/merge-29354/$RUN_ID"
PY="$ROOT/envs/physxgen/bin/python"
mkdir -p "$STAGE/physxnet/finaljson" "$STAGE/physxnet/partseg/29354/objs" "$STAGE/home/.cache" "$LOG"

cp "$INPUT/annotation/29354.json" "$STAGE/physxnet/finaljson/29354.json"
cp "$INPUT/objs/"*.obj "$STAGE/physxnet/partseg/29354/objs/"
ln -s "$CLIP_CACHE" "$STAGE/home/.cache/clip"

{
  echo "run_id=$RUN_ID"
  echo "source=$SRC"
  git -C "$SRC" rev-parse HEAD 2>/dev/null || true
  echo "stage=$STAGE"
  echo "log=$LOG"
  echo "clip_cache=$CLIP_CACHE"
  stat -c '%n %s' "$CLIP_CACHE/ViT-L-14.pt"
  sha256sum "$CLIP_CACHE/ViT-L-14.pt"
  echo "CUDA_VISIBLE_DEVICES=1"
  nvidia-smi --query-gpu=index,uuid,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits
  nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv,noheader,nounits
  echo "staged_inputs"
  find "$STAGE/physxnet" -type f -printf '%P %s bytes\n' | sort
  echo "command=$PY $SRC/dataset_toolkits/merge_property.py --index 0 --range 1 --datapath $STAGE/physxnet"
} > "$LOG/preflight.log" 2>&1

# Preserve the GPU-1 compute-process guard before launching the one allowed run.
GPU1_UUID=$(nvidia-smi --query-gpu=index,uuid --format=csv,noheader,nounits 2>>"$LOG/preflight.log" | awk -F',' '{gpu_index=$1; gsub(/^[ \t]+|[ \t]+$/, "", gpu_index); gpu_uuid=$2; gsub(/^[ \t]+|[ \t]+$/, "", gpu_uuid); if (gpu_index=="1") print gpu_uuid}')
if test -z "$GPU1_UUID"; then
  echo "ABORT_REASON: GPU index 1 UUID could not be resolved" | tee "$LOG/abort_reason.txt"
  exit 2
fi
if nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv,noheader,nounits 2>>"$LOG/preflight.log" | grep -F "$GPU1_UUID" > "$LOG/gpu1_compute_processes.txt"; then
  echo "ABORT_REASON: GPU 1 has a compute process" | tee "$LOG/abort_reason.txt"
  exit 3
fi

echo "$GPU1_UUID" > "$LOG/gpu1_uuid.txt"
set +e
(
  cd "$STAGE" || exit 10
  CUDA_VISIBLE_DEVICES=1 HOME="$STAGE/home" TORCH_HOME="$STAGE/home/.cache" \
    "$PY" "$SRC/dataset_toolkits/merge_property.py" --index 0 --range 1 --datapath "$STAGE/physxnet"
) > "$LOG/stdout.log" 2> "$LOG/stderr.log"
RC=$?
set -e
echo "$RC" > "$LOG/exit_code.txt"

if test "$RC" -eq 0; then
  {
    for f in "$STAGE/phy_dataset/29354/model.obj" "$STAGE/phy_dataset/29354/clip.npy" "$STAGE/phy_dataset/29354/clip_ind_new.npy" "$STAGE/phy_dataset/29354/otherproperty.npy"; do
      test -f "$f" || { echo "missing=$f"; exit 20; }
      stat -c '%n %s' "$f"
      sha256sum "$f"
    done
    "$PY" - "$STAGE" <<'PY'
import pathlib, sys, numpy as np
root=pathlib.Path(sys.argv[1])/'phy_dataset/29354'
for name in ('clip.npy','clip_ind_new.npy','otherproperty.npy'):
 a=np.load(root/name, allow_pickle=False)
 print(f'{name} shape={a.shape} dtype={a.dtype} ndim={a.ndim}')
PY
  } > "$LOG/output_verification.log" 2>&1
  VERIFY_RC=$?
  echo "$VERIFY_RC" > "$LOG/output_verification_exit_code.txt"
else
  echo "merge_failed; no retry performed" > "$LOG/output_verification.log"
fi
exit "$RC"
