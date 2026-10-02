#!/usr/bin/env bash
# Uses existing GT-only USD. It never regenerates URDF/USD or reads prediction artifacts.
set -euo pipefail
ROOT=/home/minsujo/Desktop/SH/PHYSx
ISAAC="$ROOT/tools/isaac-sim"
REPO="$ROOT/repro-records"
INPUT_STAGE="$ROOT/staging/gt-only-isaac-control-20261002T072614Z-gt-only-control"
if [ "$#" -gt 0 ]; then INPUT_STAGE="$1"; fi
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-gt-only-physics-control"
LOG="$ROOT/logs/gt-only-isaac-physics-control/$RUN_ID"
STAGE="$ROOT/staging/gt-only-isaac-physics-control-$RUN_ID"
mkdir -p "$LOG" "$STAGE"
exec > >(tee "$LOG/runner.stdout.log") 2> >(tee "$LOG/runner.stderr.log" >&2)
printf 'run_id=%s\ninput_stage=%s\n' "$RUN_ID" "$INPUT_STAGE"
nvidia-smi --query-gpu=index,uuid,name,driver_version --format=csv,noheader,nounits | tee "$LOG/gpu_inventory.csv"
GPU_UUID="$(nvidia-smi --query-gpu=index,uuid --format=csv,noheader,nounits | awk -F, '$1 ~ /^1$/ {gsub(/^ +| +$/, "", $2); print $2}')"
[ -n "$GPU_UUID" ] || { printf 'GPU 1 UUID not found\n' >&2; exit 1; }
if nvidia-smi --query-compute-apps=gpu_uuid,pid --format=csv,noheader,nounits | awk -F, -v uuid="$GPU_UUID" '$1 ~ uuid {found=1} END {exit !found}'; then
  printf 'GPU 1 has a compute process; aborting without simulation\n' >&2; exit 1
fi
printf 'physical_gpu_index=1\nphysical_gpu_uuid=%s\n' "$GPU_UUID" | tee "$LOG/gpu_selection.txt"

set +e
"$ISAAC/python.sh" --no-ros-env "$REPO/04_PhysX-3D/04_한계및후속작업/2026-10-02_GT_only_IsaacSim_물리구동_대조군/gt_only_physics_control.py" \
  --root "$ROOT" --input-stage "$INPUT_STAGE" --stage "$STAGE" \
  >"$LOG/child.stdout.log" 2>"$LOG/child.stderr.log"
rc=$?
set -e
printf '%s\n' "$rc" >"$LOG/exit_code.txt"
if [ "$rc" -eq 0 ] && rg -qx 'GT_ONLY_PHYSICS_CONTROL=PASS' "$LOG/child.stdout.log"; then
  printf 'GT_ONLY_PHYSICS_CONTROL=PASS\n'
else
  printf 'GT_ONLY_PHYSICS_CONTROL=FAIL child_rc=%s log=%s\n' "$rc" "$LOG" >&2
  exit "$rc"
fi
