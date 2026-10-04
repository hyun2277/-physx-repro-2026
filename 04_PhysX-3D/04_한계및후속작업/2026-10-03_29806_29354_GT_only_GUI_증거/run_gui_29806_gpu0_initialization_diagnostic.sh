#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/minsujo/Desktop/SH/PHYSx
REPO="$ROOT/repro-records"
DIR="$REPO/04_PhysX-3D/04_한계및후속작업/2026-10-03_29806_29354_GT_only_GUI_증거"
ISAAC="$ROOT/tools/isaac-sim"
URDF="$ROOT/staging/gt-only-isaac-control-20261002T072614Z-gt-only-control/29806/gt_29806.urdf"
USD="$ROOT/staging/gt-only-isaac-control-20261002T072614Z-gt-only-control/29806/gt_29806/gt_29806.usda"
UUID=GPU-ff124b39-8b48-7d2a-bf74-bf6a5c8f1716
BUS=00000000:01:00.0
HUMAN_GATE="$DIR/29806_static_mapping_human_pass.json"

fail(){ printf 'FAILED stage=%s LOG_DIR=%s STAGING_DIR=%s\n' "$1" "${LOG_DIR:-not-created}" "${STAGING_DIR:-not-created}" >&2; exit "${2:-1}"; }
[[ -n "${DISPLAY:-}" ]] || fail display_preflight 3
python3 - "$HUMAN_GATE" <<'PY_GATE' || fail static_human_gate 13
import json,sys
r=json.load(open(sys.argv[1]))
assert r["status"]=="STATIC_MAPPING_AUTOMATION_AND_HUMAN_PASS"
assert r["capture_sha256"]=="867aefac19ee66c1e0034518c6996fd82b1f66962ac93618fa83c00697aaf1fd"
assert r["physics_steps"]==0
PY_GATE
command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null && command -v xrandr >/dev/null || fail capture_tools 4
[[ "$(sha256sum "$USD"|awk '{print $1}')" == 5da6eb5823de2a8da1d7896ad047c8a73b2f25c79b60bd606afe912dd1b0891a ]] || fail usd_hash 5
[[ "$(sha256sum "$URDF"|awk '{print $1}')" == 99ee19188ec969488e63ae2504f3ecf04f7de73071e523ec9e4f231fb68855c6 ]] || fail urdf_hash 6

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-29806-gpu0-initialization-diagnostic-$(cat /proc/sys/kernel/random/uuid)"
LOG_DIR="$ROOT/logs/isaac-gui-usd-visual-validation/$RUN_ID"
STAGING_DIR="$ROOT/staging/isaac-gui-usd-visual-validation-$RUN_ID"
mkdir -p "$LOG_DIR" "$STAGING_DIR"
trap 'rc=$?; if ((rc)); then printf "FAILED stage=runner_exit_%s LOG_DIR=%s STAGING_DIR=%s\n" "$rc" "$LOG_DIR" "$STAGING_DIR" >&2; fi' EXIT
echo "LOG_DIR=$LOG_DIR"; echo "STAGING_DIR=$STAGING_DIR"

nvidia-smi --query-gpu=index,uuid,pci.bus_id,name,memory.total,memory.used,memory.free --format=csv,noheader >"$LOG_DIR/gpu.csv"
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv,noheader >"$LOG_DIR/processes.csv"
read -r actual_uuid actual_bus < <(awk -F', *' '$1==0 {print $2, $3}' "$LOG_DIR/gpu.csv")
[[ "$actual_uuid" == "$UUID" && "$actual_bus" == "$BUS" ]] || fail gpu_identity 7
! awk -F', *' -v u="$UUID" '$1==u {found=1} END {exit !found}' "$LOG_DIR/processes.csv" || fail gpu0_busy 8
xdpyinfo >/dev/null 2>&1 || fail x11_connection 9
geometry="$(xrandr --current|awk '/ connected primary /{for(i=1;i<=NF;i++)if($i~/^[0-9]+x[0-9]+\+[0-9]+\+[0-9]+$/){print $i;exit}}')"
[[ "$geometry" =~ ^([0-9]+x[0-9]+)\+([0-9]+)\+([0-9]+)$ ]] || fail xrandr_geometry 10
size=${BASH_REMATCH[1]}; offset=${BASH_REMATCH[2]},${BASH_REMATCH[3]}
printf '{"status":"PASS","gpu_index":0,"uuid":"%s","pci":"%s","multi_gpu":false,"p2p":false}\n' "$actual_uuid" "$actual_bus" >"$LOG_DIR/preflight.json"

unset CUDA_VISIBLE_DEVICES NVIDIA_VISIBLE_DEVICES
cmd=("$ISAAC/python.sh" --no-ros-env "$DIR/gui_29806_end_to_end_physics_video.py" --root "$ROOT" --input-usd "$USD" --input-urdf "$URDF" --run-dir "$STAGING_DIR" --capture-size "$size" --capture-offset "$offset" --initialization-diagnostic)
printf '%q ' "${cmd[@]}" >"$LOG_DIR/command.txt"; printf '\n' >>"$LOG_DIR/command.txt"
set +e
timeout --signal=INT --kill-after=30s 300s "${cmd[@]}" > >(tee "$LOG_DIR/stdout.log") 2> >(tee "$LOG_DIR/stderr.log" >&2) &
child_pid=$!
(
  startup_deadline=$(( $(date +%s) + 180 ))
  while kill -0 "$child_pid" 2>/dev/null; do
    heartbeat="$STAGING_DIR/gui_heartbeat.json"
    phase_file="$STAGING_DIR/runner_phase.txt"
    if [[ -f "$heartbeat" ]]; then
      age=$(( $(date +%s) - $(stat -c %Y "$heartbeat") ))
      if (( age > 5 )); then
        printf 'WATCHDOG_FAIL heartbeat_stale_s=%s phase=%s\n' "$age" "$(cat "$phase_file" 2>/dev/null || echo unknown)" >"$LOG_DIR/watchdog_failure.txt"
        kill -INT "$child_pid" 2>/dev/null || true
        sleep 5
        kill -TERM "$child_pid" 2>/dev/null || true
        exit 70
      fi
    elif (( $(date +%s) > startup_deadline )); then
      printf 'WATCHDOG_FAIL no_heartbeat_within_180s\n' >"$LOG_DIR/watchdog_failure.txt"
      kill -INT "$child_pid" 2>/dev/null || true
      exit 71
    fi
    sleep 1
  done
) &
watchdog_pid=$!
wait "$child_pid"; rc=$?
kill "$watchdog_pid" 2>/dev/null || true
wait "$watchdog_pid" 2>/dev/null || true
set -e
printf '%s\n' "$rc" >"$LOG_DIR/exit_code.txt"
if ((rc==0)); then
  [[ -f "$STAGING_DIR/initialization_diagnostic_complete.json" ]] || fail diagnostic_complete_marker 11
  printf 'INITIALIZATION_DIAGNOSTIC_COMPLETE LOG_DIR=%s STAGING_DIR=%s\n' "$LOG_DIR" "$STAGING_DIR"
else
  [[ -f "$STAGING_DIR/initialization_diagnostic_report.json" ]] || fail missing_diagnostic_report "$rc"
  printf 'INITIALIZATION_DIAGNOSTIC_STOPPED rc=%s LOG_DIR=%s STAGING_DIR=%s\n' "$rc" "$LOG_DIR" "$STAGING_DIR" >&2
  exit "$rc"
fi
