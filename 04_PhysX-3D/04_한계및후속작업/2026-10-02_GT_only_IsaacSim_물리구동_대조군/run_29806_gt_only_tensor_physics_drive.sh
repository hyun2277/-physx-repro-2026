#!/usr/bin/env bash
# GT-only controlled-material PhysX drive for 29806; no generated/predicted output is read.
set -euo pipefail
ROOT=/home/minsujo/Desktop/SH/PHYSx
REPO="$ROOT/repro-records"
ISAAC="$ROOT/tools/isaac-sim"
USD="$ROOT/staging/gt-only-isaac-control-20261002T072614Z-gt-only-control/29806/gt_29806/gt_29806.usda"
ID="$(date -u +%Y%m%dT%H%M%SZ)-29806-tensor-drive"
LOG="$ROOT/logs/gt-only-isaac-tensor-drive/$ID"
STAGE="$ROOT/staging/gt-only-isaac-tensor-drive-$ID"
mkdir -p "$LOG" "$STAGE"
exec > >(tee "$LOG/runner.stdout.log") 2> >(tee "$LOG/runner.stderr.log" >&2)
[ -f "$USD" ] || { echo 'missing USD' >&2; exit 1; }
nvidia-smi --query-gpu=index,uuid,name,driver_version --format=csv,noheader,nounits | tee "$LOG/gpu_inventory.csv"
UUID="$(nvidia-smi --query-gpu=index,uuid --format=csv,noheader,nounits | awk -F, '$1~/^1$/{gsub(/^ +| +$/,"",$2);print $2}')"
[ -n "$UUID" ] || { echo 'GPU 1 UUID missing' >&2; exit 1; }
if nvidia-smi --query-compute-apps=gpu_uuid,pid --format=csv,noheader,nounits | awk -F, -v u="$UUID" '$1~u{f=1}END{exit !f}'; then echo 'GPU 1 busy' >&2; exit 1; fi
printf 'physical_gpu_index=1\nphysical_gpu_uuid=%s\nCUDA_VISIBLE_DEVICES=1\nP2P=disabled\nmulti_gpu=false\n' "$UUID" | tee "$LOG/gpu_selection.txt"
set +e
CUDA_VISIBLE_DEVICES=1 "$ISAAC/python.sh" --no-ros-env "$REPO/04_PhysX-3D/04_한계및후속작업/2026-10-02_GT_only_IsaacSim_물리구동_대조군/gt_only_tensor_physics_drive_29806.py" --root "$ROOT" --input-usd "$USD" --stage "$STAGE" >"$LOG/child.stdout.log" 2>"$LOG/child.stderr.log"
rc=$?
set -e
echo "$rc" > "$LOG/exit_code.txt"
if [ "$rc" -eq 0 ] && rg -qx 'GT_TENSOR_DRIVE_29806=PASS' "$LOG/child.stdout.log" && [ -s "$STAGE/physics_drive_report.json" ]; then
 echo 'GT_TENSOR_DRIVE_29806=PASS'
else
 echo "GT_TENSOR_DRIVE_29806=FAIL child_rc=$rc log=$LOG" >&2
 tail -n 80 "$LOG/child.stderr.log" >&2 || true
 exit 1
fi
