#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/home/minsujo/Desktop/SH/PHYSx; BASE="$ROOT/repro-records/04_PhysX-3D/04_한계및후속작업/2026-10-02_GT_only_IsaacSim_물리구동_대조군"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-replicator-r11-direct-gpu1"; LOG="$ROOT/logs/isaac-sim-replicator-rgb-smoke/$RUN_ID"; mkdir -p "$LOG/out"
printf 'run_id=%s\nkit=%s\nphysical_gpu=1\nCUDA_VISIBLE_DEVICES=unset\nframes=3\nrt_subframes=16\n' "$RUN_ID" "$BASE/isaac_minimal_replicator_render_r11.kit" > "$LOG/run.env"
set +e
env -u CUDA_VISIBLE_DEVICES "$ROOT/tools/isaac-sim/python.sh" --no-ros-env "$BASE/smoke_replicator_rgb_r11.py" --root "$ROOT" --out "$LOG/out" >"$LOG/stdout.log" 2>"$LOG/stderr.log"
rc=$?
set -e
if ! grep -q '^REPLICATOR_RGB_SMOKE_PASS=' "$LOG/stdout.log"; then printf 'FAIL rc=%s marker_missing log=%s\n' "$rc" "$LOG" >&2; exit 1; fi
printf 'PASS log=%s\n' "$LOG"
