#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/minsujo/Desktop/SH/PHYSx
USD="$ROOT/staging/gt-only-isaac-control-20261002T072614Z-gt-only-control/29806/gt_29806/gt_29806.usda"
EXPECTED=5da6eb5823de2a8da1d7896ad047c8a73b2f25c79b60bd606afe912dd1b0891a
UUID=GPU-ff124b39-8b48-7d2a-bf74-bf6a5c8f1716
BUS=00000000:01:00.0
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-29806-gpu0-structure-gate-$(cat /proc/sys/kernel/random/uuid)"
LOG_DIR="$ROOT/logs/isaac-gui-usd-visual-validation/$RUN_ID"
STAGING_DIR="$ROOT/staging/isaac-gui-usd-visual-validation-$RUN_ID"
mkdir -p "$LOG_DIR" "$STAGING_DIR"
echo "LOG_DIR=$LOG_DIR"
echo "STAGING_DIR=$STAGING_DIR"

[[ -n "${DISPLAY:-}" ]] || { echo 'FAILED: DISPLAY unset'; exit 3; }
[[ "$(sha256sum "$USD" | awk '{print $1}')" == "$EXPECTED" ]] || { echo 'FAILED: USD hash'; exit 4; }
nvidia-smi --query-gpu=index,uuid,pci.bus_id,memory.total,memory.used,memory.free --format=csv,noheader >"$LOG_DIR/gpu.csv"
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv,noheader >"$LOG_DIR/processes.csv"
read -r actual_uuid actual_bus < <(awk -F', *' '$1==0 {print $2, $3}' "$LOG_DIR/gpu.csv")
[[ "$actual_uuid" == "$UUID" && "$actual_bus" == "$BUS" ]] || { echo 'FAILED: GPU 0 identity'; exit 5; }
! awk -F', *' -v u="$UUID" '$1==u {found=1} END {exit !found}' "$LOG_DIR/processes.csv" || { echo 'FAILED: GPU 0 compute process present'; exit 6; }
xdpyinfo >/dev/null 2>&1 || { echo 'FAILED: X11 unavailable'; exit 7; }

cat >"$STAGING_DIR/gate_result.json" <<EOF
{"status":"PASS_STRUCTURE_AUDIT_REQUIRED","object_id":29806,"gt_only":true,"ai_prediction":false,"input_usd":"$USD","sha256":"$EXPECTED","gpu_index":0,"gpu_uuid":"$UUID","pci":"$BUS","physics_started":false,"simulation_steps":0,"capture_started":false}
EOF
echo 'STRUCTURE_GATE_PASS_PHYSICS_NOT_STARTED'
echo 'Next: inspect composed joint/body/fixed-chain mapping before enabling GUI physics.'
