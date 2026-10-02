#!/usr/bin/env bash
set -euo pipefail

PHYSX_ROOT="/home/minsujo/Desktop/SH/PHYSx"
RECORD_DIR="$PHYSX_ROOT/repro-records/04_PhysX-3D/04_한계및후속작업/2026-10-03_IsaacSim_GUI_USD_물리구동_시각검증"
KIT="$PHYSX_ROOT/tools/isaac-sim/kit/kit"
EXPERIENCE="$RECORD_DIR/isaac_gui_cube_gpu0_presentation.kit"
SETUP_SCRIPT="$RECORD_DIR/gui_visual_validation_setup.py"
EXPECTED_UUID="GPU-ff124b39-8b48-7d2a-bf74-bf6a5c8f1716"
EXPECTED_BUS="00000000:01:00.0"

[[ -n "${DISPLAY:-}" ]] || { echo "DISPLAY is empty; use the logged-in Linux desktop terminal." >&2; exit 3; }
for required in "$KIT" "$EXPERIENCE" "$SETUP_SCRIPT"; do
  [[ -f "$required" ]] || { echo "missing required file: $required" >&2; exit 4; }
done

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-cube-gpu0-$(cat /proc/sys/kernel/random/uuid)"
LOG_DIR="$PHYSX_ROOT/logs/isaac-gui-usd-visual-validation/$RUN_ID"
STAGING_DIR="$PHYSX_ROOT/staging/isaac-gui-usd-visual-validation-$RUN_ID"
mkdir -p "$LOG_DIR" "$STAGING_DIR/screenshots"
echo "LOG_DIR=$LOG_DIR"
echo "SCREENSHOT_DIR=$STAGING_DIR/screenshots"
echo "Scope: GPU 0 GUI cube presentation only; no USD asset and no physics simulation."

nvidia-smi --query-gpu=index,uuid,pci.bus_id,name,memory.total,memory.used,memory.free \
  --format=csv,noheader > "$LOG_DIR/nvidia_smi_inventory.csv"
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory \
  --format=csv,noheader > "$LOG_DIR/compute_processes.csv"
gpu0_line="$(awk -F', *' '$1 == 0 {print; exit}' "$LOG_DIR/nvidia_smi_inventory.csv")"
actual_uuid="$(awk -F', *' '$1 == 0 {print $2; exit}' "$LOG_DIR/nvidia_smi_inventory.csv")"
actual_bus="$(awk -F', *' '$1 == 0 {print $3; exit}' "$LOG_DIR/nvidia_smi_inventory.csv")"
[[ -n "$gpu0_line" && "$actual_uuid" == "$EXPECTED_UUID" && "$actual_bus" == "$EXPECTED_BUS" ]] || {
  echo "GPU 0 identity mismatch; refusing to start Isaac." >&2
  exit 5
}
if awk -F', *' -v uuid="$EXPECTED_UUID" '$1 == uuid {found=1} END {exit !found}' "$LOG_DIR/compute_processes.csv"; then
  echo "GPU 0 has a compute process; refusing to start Isaac." >&2
  exit 6
fi
cat > "$LOG_DIR/marker_gpu0_preflight.json" <<EOF
{
  "status": "PASS",
  "gpu_index": 0,
  "uuid": "$actual_uuid",
  "pci_bus": "$actual_bus",
  "inventory": "$gpu0_line",
  "compute_process_count": 0
}
EOF
nvidia-smi > "$LOG_DIR/nvidia_smi_full.txt"
{
  printf 'DISPLAY=%s\n' "${DISPLAY-<unset>}"
  printf 'WAYLAND_DISPLAY=%s\n' "${WAYLAND_DISPLAY-<unset>}"
  printf 'XDG_SESSION_TYPE=%s\n' "${XDG_SESSION_TYPE-<unset>}"
  printf 'XAUTHORITY=%s\n' "${XAUTHORITY-<unset>}"
} > "$LOG_DIR/display_environment.txt"
xrandr --listproviders > "$LOG_DIR/xrandr_providers.txt" 2>&1 || true
xrandr --query > "$LOG_DIR/xrandr_query.txt" 2>&1 || true

# Leave both physical devices visible for Vulkan/CUDA identity matching, but
# select only physical GPU 0 for this renderer-only gate.
unset CUDA_VISIBLE_DEVICES
unset NVIDIA_VISIBLE_DEVICES
export PHYSX_GUI_MODE=cube
export PHYSX_GUI_RUN_DIR="$LOG_DIR"
{
  printf 'renderer.activeGpu=0\n'
  printf 'renderer.multiGpu.enabled=false\n'
  printf 'renderer.multiGpu.autoEnable=false\n'
  printf 'physics_loaded=false (experience has no PhysX dependencies)\n'
} > "$LOG_DIR/gpu_selection_effective.txt"

printf '%q ' "$KIT" "$EXPERIENCE" --exec "$SETUP_SCRIPT" \
  --/renderer/activeGpu=0 \
  --/renderer/multiGpu/enabled=false \
  --/renderer/multiGpu/autoEnable=false \
  --/app/window/hideUi=false > "$LOG_DIR/command.txt"
printf '\n' >> "$LOG_DIR/command.txt"

set +e
"$KIT" "$EXPERIENCE" --exec "$SETUP_SCRIPT" \
  --/renderer/activeGpu=0 \
  --/renderer/multiGpu/enabled=false \
  --/renderer/multiGpu/autoEnable=false \
  --/app/window/hideUi=false \
  > >(tee "$LOG_DIR/stdout.log") 2> >(tee "$LOG_DIR/stderr.log" >&2)
RC=$?
set -e
printf '%s\n' "$RC" > "$LOG_DIR/exit_code.txt"

required_markers=(marker_gpu0_preflight.json marker_app_startup.json marker_omni_usd_import.json marker_gui_mode.json marker_cube_created.json marker_cube_stage_lookup.json marker_summary.json)
failed=0
for marker in "${required_markers[@]}"; do
  [[ -s "$LOG_DIR/$marker" ]] || { echo "MISSING_AUTOMATION_MARKER=$marker" >&2; failed=1; }
done
if [[ -s "$LOG_DIR/marker_gui_mode.json" ]] && ! grep -Fq '"headless_setting": false' "$LOG_DIR/marker_gui_mode.json"; then
  echo "GUI_HEADLESS_FALSE_MARKER_MISSING" >&2
  failed=1
fi
kit_log_path="$(awk -F'Logging to file: ' '/Logging to file:/{print $2; exit}' "$LOG_DIR/stdout.log")"
[[ -n "$kit_log_path" ]] && printf '%s\n' "$kit_log_path" > "$LOG_DIR/kit_log_path.txt"
error_pattern='Failed to find a graphics and/or presenting queue|createSwapchain failed|backbuffers are not initialized|Failed to initialize graphics environment|Failed to create any GPU devices'
if rg -q "$error_pattern" "$LOG_DIR/stdout.log" "$LOG_DIR/stderr.log" 2>/dev/null || { [[ -f "$kit_log_path" ]] && rg -q "$error_pattern" "$kit_log_path"; }; then
  echo "RENDERER_SURFACE_FAILURE" >&2
  failed=1
fi
if [[ "$failed" -eq 0 ]]; then
  printf '%s\n' '{"status":"PASS","swapchain_errors":0,"backbuffer_errors":0,"human_verified":false}' > "$LOG_DIR/marker_renderer_surface_clean.json"
fi
if [[ "$failed" -ne 0 ]]; then
  printf '%s\n' 'FAIL_AUTOMATION_OR_RENDERER_SURFACE' > "$LOG_DIR/automation_status.txt"
  exit 10
fi
printf '%s\n' 'PASS_AUTOMATION_MARKERS_HUMAN_GUI_CHECK_REQUIRED' > "$LOG_DIR/automation_status.txt"
echo "Automation markers passed. GUI_VISIBLE remains unconfirmed until a human verifies the lit cube, viewport, and /World/VisibleCube in Stage tree."
exit "$RC"
