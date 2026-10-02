#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/minsujo/Desktop/SH/PHYSx"
REPO="$ROOT/repro-records"
RECORD_DIR="$REPO/04_PhysX-3D/04_한계및후속작업/2026-10-03_IsaacSim_GUI_USD_물리구동_시각검증"
ISAAC="$ROOT/tools/isaac-sim"
USD="$ROOT/staging/gt-only-isaac-control-20261002T072614Z-gt-only-control/10163/gt_10163/gt_10163.usda"
EXPECTED_SHA256="72cee88ff5ac563e89c34e4028a9a3fe3d8b839d40f88fed4ef048e3f4fab23b"
EXPECTED_UUID="GPU-ff124b39-8b48-7d2a-bf74-bf6a5c8f1716"
EXPECTED_BUS="00000000:01:00.0"

[[ -n "${DISPLAY:-}" ]] || { echo "DISPLAY is empty; use the logged-in Linux GUI terminal." >&2; exit 3; }
for required in "$USD" "$ISAAC/python.sh" "$RECORD_DIR/gui_10163_gt_only_tensor_physics.py" "$RECORD_DIR/isaac_gui_10163_gpu0_tensor_physics.kit"; do
  [[ -f "$required" ]] || { echo "missing required file: $required" >&2; exit 4; }
done
[[ "$(sha256sum "$USD" | awk '{print $1}')" == "$EXPECTED_SHA256" ]] || {
  echo "10163 USD SHA256 mismatch" >&2; exit 5;
}

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-10163-gpu0-gui-physics-$(cat /proc/sys/kernel/random/uuid)"
LOG_DIR="$ROOT/logs/isaac-gui-usd-visual-validation/$RUN_ID"
STAGING_DIR="$ROOT/staging/isaac-gui-usd-visual-validation-$RUN_ID"
mkdir -p "$LOG_DIR" "$STAGING_DIR/screenshots"
echo "LOG_DIR=$LOG_DIR"
echo "STAGING_DIR=$STAGING_DIR"
echo "SCREENSHOT_DIR=$STAGING_DIR/screenshots"
echo "Scope: 10163 GT-only GPU 0 GUI physics control; not AI prediction."

nvidia-smi --query-gpu=index,uuid,pci.bus_id,name,memory.total,memory.used,memory.free \
  --format=csv,noheader > "$LOG_DIR/nvidia_smi_inventory.csv"
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory \
  --format=csv,noheader > "$LOG_DIR/compute_processes.csv"
actual_uuid="$(awk -F', *' '$1 == 0 {print $2; exit}' "$LOG_DIR/nvidia_smi_inventory.csv")"
actual_bus="$(awk -F', *' '$1 == 0 {print $3; exit}' "$LOG_DIR/nvidia_smi_inventory.csv")"
[[ "$actual_uuid" == "$EXPECTED_UUID" && "$actual_bus" == "$EXPECTED_BUS" ]] || {
  echo "GPU 0 identity mismatch" >&2; exit 6;
}
if awk -F', *' -v uuid="$EXPECTED_UUID" '$1 == uuid {found=1} END {exit !found}' "$LOG_DIR/compute_processes.csv"; then
  echo "GPU 0 has another compute process; refusing to start" >&2; exit 7
fi

display_geometry="$(xrandr --current | awk '/ connected primary / {for(i=1;i<=NF;i++) if($i ~ /^[0-9]+x[0-9]+\+[0-9]+\+[0-9]+$/){print $i; exit}}')"
[[ "$display_geometry" =~ ^([0-9]+x[0-9]+)\+([0-9]+)\+([0-9]+)$ ]] || {
  echo "could not determine primary display capture geometry: $display_geometry" >&2; exit 8;
}
capture_size="${BASH_REMATCH[1]}"
capture_offset="${BASH_REMATCH[2]},${BASH_REMATCH[3]}"
printf '{"status":"PASS","gpu_index":0,"uuid":"%s","pci_bus":"%s","compute_process_count":0,"capture_size":"%s","capture_offset":"%s"}\n' \
  "$actual_uuid" "$actual_bus" "$capture_size" "$capture_offset" > "$LOG_DIR/marker_gpu0_preflight.json"

unset CUDA_VISIBLE_DEVICES
unset NVIDIA_VISIBLE_DEVICES
printf '%q ' "$ISAAC/python.sh" --no-ros-env "$RECORD_DIR/gui_10163_gt_only_tensor_physics.py" \
  --root "$ROOT" --input-usd "$USD" --run-dir "$STAGING_DIR" \
  --capture-size "$capture_size" --capture-offset "$capture_offset" > "$LOG_DIR/command.txt"
printf '\n' >> "$LOG_DIR/command.txt"

set +e
"$ISAAC/python.sh" --no-ros-env "$RECORD_DIR/gui_10163_gt_only_tensor_physics.py" \
  --root "$ROOT" --input-usd "$USD" --run-dir "$STAGING_DIR" \
  --capture-size "$capture_size" --capture-offset "$capture_offset" \
  > >(tee "$LOG_DIR/child.stdout.log") 2> >(tee "$LOG_DIR/child.stderr.log" >&2)
child_rc=$?
set -e
printf '%s\n' "$child_rc" > "$LOG_DIR/child_exit_code.txt"
if [[ "$child_rc" -ne 0 ]] || ! rg -qx 'GT_GUI_TENSOR_PHYSICS_CAPTURE=AUTOMATED_PASS_HUMAN_REVIEW_REQUIRED' "$LOG_DIR/child.stdout.log"; then
  echo "10163 GUI physics pretest/capture failed; see $LOG_DIR" >&2
  [[ "$child_rc" -ne 0 ]] && exit "$child_rc"
  exit 9
fi

python3 "$RECORD_DIR/validate_10163_gpu0_gui_video.py" --run-dir "$STAGING_DIR" \
  > "$LOG_DIR/video_validation.stdout.log" 2> "$LOG_DIR/video_validation.stderr.log"
printf '%s\n' 'AUTOMATED_PASS_HUMAN_GUI_VIDEO_REVIEW_REQUIRED' > "$LOG_DIR/status.txt"
echo "Automated checks passed. Human review is still required before GUI physics visibility is PASS."
