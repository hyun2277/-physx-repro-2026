#!/usr/bin/env bash
# Runs only a no-drive runtime PhysicsScene registration smoke on physical GPU 1.
set -euo pipefail
ROOT=/home/minsujo/Desktop/SH/PHYSx
REPO="$ROOT/repro-records"
ISAAC="$ROOT/tools/isaac-sim"
INPUT_USD="$ROOT/staging/gt-only-isaac-control-20261002T072614Z-gt-only-control/10163/gt_10163/gt_10163.usda"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-physics-scene-registration"
LOG="$ROOT/logs/isaac-sim-physics-scene-registration/$RUN_ID"
mkdir -p "$LOG"
exec > >(tee "$LOG/runner.stdout.log") 2> >(tee "$LOG/runner.stderr.log" >&2)
printf 'run_id=%s\ninput_usd=%s\n' "$RUN_ID" "$INPUT_USD"
[ -f "$INPUT_USD" ] || { printf 'input USD is missing\n' >&2; exit 1; }
nvidia-smi --query-gpu=index,uuid,name,driver_version --format=csv,noheader,nounits | tee "$LOG/gpu_inventory.csv"
GPU_UUID="$(nvidia-smi --query-gpu=index,uuid --format=csv,noheader,nounits | awk -F, '$1 ~ /^1$/ {gsub(/^ +| +$/, "", $2); print $2}')"
[ -n "$GPU_UUID" ] || { printf 'GPU 1 UUID not found\n' >&2; exit 1; }
if nvidia-smi --query-compute-apps=gpu_uuid,pid --format=csv,noheader,nounits | awk -F, -v uuid="$GPU_UUID" '$1 ~ uuid {found=1} END {exit !found}'; then
  printf 'GPU 1 has a compute process; aborting without smoke\n' >&2; exit 1
fi
printf 'physical_gpu_index=1\nphysical_gpu_uuid=%s\nCUDA_VISIBLE_DEVICES=1\n' "$GPU_UUID" | tee "$LOG/gpu_selection.txt"
set +e
CUDA_VISIBLE_DEVICES=1 "$ISAAC/python.sh" --no-ros-env \
  "$REPO/04_PhysX-3D/04_한계및후속작업/2026-10-02_IsaacSim_PhysicsScene_등록Smoke/physics_scene_registration_smoke.py" \
  --root "$ROOT" --input-usd "$INPUT_USD" --log-dir "$LOG" \
  >"$LOG/child.stdout.log" 2>"$LOG/child.stderr.log"
rc=$?
set -e
printf '%s\n' "$rc" >"$LOG/exit_code.txt"
if [ "$rc" -eq 0 ] && rg -qx 'PHYSICS_SCENE_SMOKE=PASS' "$LOG/child.stdout.log"; then
  printf 'PHYSICS_SCENE_SMOKE=PASS\n'
else
  printf 'PHYSICS_SCENE_SMOKE=FAIL child_rc=%s log=%s\n' "$rc" "$LOG" >&2
  exit "$rc"
fi
