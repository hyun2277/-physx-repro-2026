#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-cube}"
if [[ "$MODE" != "cube" && "$MODE" != "10163" ]]; then
  echo "usage: $0 {cube|10163}" >&2
  exit 2
fi

PHYSX_ROOT="/home/minsujo/Desktop/SH/PHYSx"
RECORD_DIR="$PHYSX_ROOT/repro-records/04_PhysX-3D/04_한계및후속작업/2026-10-03_IsaacSim_GUI_USD_물리구동_시각검증"
ISAAC_ROOT="$PHYSX_ROOT/tools/isaac-sim"
KIT="$ISAAC_ROOT/kit/kit"
EXPERIENCE="$RECORD_DIR/isaac_gui_visual_validation.kit"
SETUP_SCRIPT="$RECORD_DIR/gui_visual_validation_setup.py"

if [[ -z "${DISPLAY:-}" ]]; then
  echo "DISPLAY is empty; run this command in the logged-in Linux desktop terminal." >&2
  exit 3
fi
for required in "$KIT" "$EXPERIENCE" "$SETUP_SCRIPT"; do
  [[ -f "$required" ]] || { echo "missing required file: $required" >&2; exit 4; }
done

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-${MODE}-$(cat /proc/sys/kernel/random/uuid)"
LOG_DIR="$PHYSX_ROOT/logs/isaac-gui-usd-visual-validation/$RUN_ID"
STAGING_DIR="$PHYSX_ROOT/staging/isaac-gui-usd-visual-validation-$RUN_ID"
SCREENSHOT_DIR="$STAGING_DIR/screenshots"
mkdir -p "$LOG_DIR" "$SCREENSHOT_DIR"

echo "LOG_DIR=$LOG_DIR"
echo "STAGING_DIR=$STAGING_DIR"
echo "SCREENSHOT_DIR=$SCREENSHOT_DIR"
echo "Human check is mandatory; this runner does not mark the GUI visible."

nvidia-smi --query-gpu=index,uuid,pci.bus_id,name,memory.total,memory.free \
  --format=csv,noheader > "$LOG_DIR/nvidia_smi_inventory.csv"
nvidia-smi > "$LOG_DIR/nvidia_smi_full.txt"

export CUDA_VISIBLE_DEVICES=1
export PHYSX_GUI_MODE="$MODE"
export PHYSX_GUI_RUN_DIR="$LOG_DIR"

printf '%q ' "$KIT" "$EXPERIENCE" --exec "$SETUP_SCRIPT" \
  --/renderer/multiGpu/enabled=false \
  --/renderer/multiGpu/autoEnable=false \
  --/renderer/activeGpu=0 \
  --/physics/cudaDevice=0 \
  --/app/window/hideUi=false \
  > "$LOG_DIR/command.txt"
printf '\n' >> "$LOG_DIR/command.txt"

set +e
"$KIT" "$EXPERIENCE" --exec "$SETUP_SCRIPT" \
  --/renderer/multiGpu/enabled=false \
  --/renderer/multiGpu/autoEnable=false \
  --/renderer/activeGpu=0 \
  --/physics/cudaDevice=0 \
  --/app/window/hideUi=false \
  > >(tee "$LOG_DIR/stdout.log") \
  2> >(tee "$LOG_DIR/stderr.log" >&2)
RC=$?
set -e
printf '%s\n' "$RC" > "$LOG_DIR/exit_code.txt"
exit "$RC"
