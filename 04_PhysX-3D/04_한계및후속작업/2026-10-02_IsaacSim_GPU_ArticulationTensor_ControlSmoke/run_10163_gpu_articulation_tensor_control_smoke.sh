#!/usr/bin/env bash
# Runs one bounded GT-only tensor-control smoke on physical GPU 1; it never sweeps a joint or saves the USD.
set -euo pipefail
ROOT=/home/minsujo/Desktop/SH/PHYSx
REPO="$ROOT/repro-records"
ISAAC="$ROOT/tools/isaac-sim"
INPUT_USD="$ROOT/staging/gt-only-isaac-control-20261002T072614Z-gt-only-control/10163/gt_10163/gt_10163.usda"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-10163-gpu-tensor-control"
LOG="$ROOT/logs/isaac-sim-gpu-articulation-tensor-control/$RUN_ID"
mkdir -p "$LOG"
exec > >(tee "$LOG/runner.stdout.log") 2> >(tee "$LOG/runner.stderr.log" >&2)
printf 'run_id=%s\ninput_usd=%s\n' "$RUN_ID" "$INPUT_USD"
[ -f "$INPUT_USD" ] || { printf 'input USD is missing\n' >&2; exit 1; }
nvidia-smi --query-gpu=index,uuid,name,driver_version --format=csv,noheader,nounits | tee "$LOG/gpu_inventory.csv"
GPU_UUID="$(nvidia-smi --query-gpu=index,uuid --format=csv,noheader,nounits | awk -F, '$1 ~ /^1$/ {gsub(/^ +| +$/, "", $2); print $2}')"
[ -n "$GPU_UUID" ] || { printf 'GPU 1 UUID not found\n' >&2; exit 1; }
if nvidia-smi --query-compute-apps=gpu_uuid,pid --format=csv,noheader,nounits | awk -F, -v uuid="$GPU_UUID" '$1 ~ uuid {found=1} END {exit !found}'; then
  printf 'GPU 1 has a compute process; aborting without control smoke\n' >&2; exit 1
fi
printf 'physical_gpu_index=1\nphysical_gpu_uuid=%s\nCUDA_VISIBLE_DEVICES=1\nP2P=disabled\n' "$GPU_UUID" | tee "$LOG/gpu_selection.txt"
set +e
CUDA_VISIBLE_DEVICES=1 "$ISAAC/python.sh" --no-ros-env \
  "$REPO/04_PhysX-3D/04_한계및후속작업/2026-10-02_IsaacSim_GPU_ArticulationTensor_ControlSmoke/gpu_articulation_tensor_control_smoke.py" \
  --root "$ROOT" --input-usd "$INPUT_USD" --log-dir "$LOG" \
  >"$LOG/child.stdout.log" 2>"$LOG/child.stderr.log"
rc=$?
set -e
printf '%s\n' "$rc" >"$LOG/exit_code.txt"
if [ "$rc" -eq 0 ] && rg -qx 'GPU_TENSOR_CONTROL=PASS' "$LOG/child.stdout.log" && [ -s "$LOG/gpu_articulation_tensor_control_report.json" ]; then
  printf 'GPU_TENSOR_CONTROL=PASS\n'
else
  printf 'GPU_TENSOR_CONTROL=FAIL child_rc=%s log=%s\n' "$rc" "$LOG" >&2
  exit "${rc:-1}"
fi
