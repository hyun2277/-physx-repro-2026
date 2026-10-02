#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/minsujo/Desktop/SH/PHYSx
REPO="$ROOT/repro-records"
DIR="$REPO/04_PhysX-3D/04_한계및후속작업/2026-10-03_29806_29354_GT_only_GUI_증거"
ISAAC="$ROOT/tools/isaac-sim"
URDF="$ROOT/staging/gt-only-isaac-control-20261002T072614Z-gt-only-control/29806/gt_29806.urdf"
USD="$ROOT/staging/gt-only-isaac-control-20261002T072614Z-gt-only-control/29806/gt_29806/gt_29806.usda"
UUID=GPU-ff124b39-8b48-7d2a-bf74-bf6a5c8f1716
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-29806-gpu0-static-mapping-$(cat /proc/sys/kernel/random/uuid)"
LOG_DIR="$ROOT/logs/isaac-gui-usd-visual-validation/$RUN_ID"
STAGING_DIR="$ROOT/staging/isaac-gui-usd-visual-validation-$RUN_ID"
SCREENSHOT_DIR="$STAGING_DIR/screenshots"
mkdir -p "$LOG_DIR" "$SCREENSHOT_DIR"
echo "LOG_DIR=$LOG_DIR"; echo "STAGING_DIR=$STAGING_DIR"; echo "SCREENSHOT_DIR=$SCREENSHOT_DIR"
[[ -n "${DISPLAY:-}" ]] || { echo 'FAILED DISPLAY unset'; exit 3; }
[[ "$(sha256sum "$USD"|awk '{print $1}')" == 5da6eb5823de2a8da1d7896ad047c8a73b2f25c79b60bd606afe912dd1b0891a ]] || exit 4
[[ "$(sha256sum "$URDF"|awk '{print $1}')" == 99ee19188ec969488e63ae2504f3ecf04f7de73071e523ec9e4f231fb68855c6 ]] || exit 5
nvidia-smi --query-gpu=index,uuid,pci.bus_id,memory.used,memory.free --format=csv,noheader >"$LOG_DIR/gpu.csv"
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv,noheader >"$LOG_DIR/processes.csv"
[[ "$(awk -F', *' '$1==0{print $2}' "$LOG_DIR/gpu.csv")" == "$UUID" ]] || exit 6
! awk -F', *' -v u="$UUID" '$1==u{found=1}END{exit !found}' "$LOG_DIR/processes.csv" || { echo 'FAILED GPU0 busy'; exit 7; }
xdpyinfo >/dev/null 2>&1 || exit 8
geometry="$(xrandr --current|awk '/ connected primary /{for(i=1;i<=NF;i++)if($i~/^[0-9]+x[0-9]+\+[0-9]+\+[0-9]+$/){print $i;exit}}')"
[[ "$geometry" =~ ^([0-9]+x[0-9]+)\+([0-9]+)\+([0-9]+)$ ]] || exit 9
size=${BASH_REMATCH[1]}; offset=${BASH_REMATCH[2]},${BASH_REMATCH[3]}
unset CUDA_VISIBLE_DEVICES NVIDIA_VISIBLE_DEVICES
cmd=("$ISAAC/python.sh" --no-ros-env "$DIR/gui_29806_end_to_end_physics_video.py" --root "$ROOT" --input-usd "$USD" --input-urdf "$URDF" --run-dir "$STAGING_DIR" --capture-size "$size" --capture-offset "$offset" --static-mapping-gate)
printf '%q ' "${cmd[@]}" >"$LOG_DIR/command.txt"; printf '\n' >>"$LOG_DIR/command.txt"
set +e
timeout --signal=INT --kill-after=20s 240s "${cmd[@]}" > >(tee "$LOG_DIR/stdout.log") 2> >(tee "$LOG_DIR/stderr.log" >&2)
rc=$?
set -e
printf '%s\n' "$rc" >"$LOG_DIR/exit_code.txt"
((rc==0)) || { echo "FAILED rc=$rc LOG_DIR=$LOG_DIR STAGING_DIR=$STAGING_DIR"; exit "$rc"; }
rg -qx 'STATIC_MAPPING_GATE=AUTOMATION_READY_HUMAN_CHECK_REQUIRED' "$LOG_DIR/stdout.log" || exit 10
[[ -s "$STAGING_DIR/static_mapping_gate.json" ]] || exit 11
echo "STATIC_MAPPING_AUTOMATION_READY_HUMAN_CHECK_REQUIRED LOG_DIR=$LOG_DIR STAGING_DIR=$STAGING_DIR"
