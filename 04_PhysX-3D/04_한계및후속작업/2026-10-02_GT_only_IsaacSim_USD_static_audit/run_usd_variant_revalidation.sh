#!/usr/bin/env bash
# Existing-USD revalidation only: it starts Isaac without a physics scene, then
# selects an already-authored Physics variant. It never imports URDF or drives a joint.
set -euo pipefail
ROOT=/home/minsujo/Desktop/SH/PHYSx
AUDIT_DIR="$ROOT/repro-records/04_PhysX-3D/04_한계및후속작업/2026-10-02_GT_only_IsaacSim_USD_static_audit"
STAGING=${1:-"$ROOT/staging/gt-only-isaac-control-20261002T072614Z-gt-only-control"}
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-usd-variant-revalidation"
LOG="$ROOT/logs/gt-only-isaac-control/$RUN_ID"
mkdir -p "$LOG"
ISAAC="$ROOT/tools/isaac-sim"
EXP="$ROOT/repro-records/04_PhysX-3D/04_한계및후속작업/2026-10-02_IsaacSim_Importer_API_진단/isaac_minimal_urdf_importer.kit"
env -u CUDA_VISIBLE_DEVICES -u CONDA_PREFIX -u CONDA_DEFAULT_ENV \
  HOME="$ISAAC/runtime-home" XDG_CACHE_HOME="$ISAAC/runtime-home/cache" \
  XDG_CONFIG_HOME="$ISAAC/runtime-home/config" XDG_DATA_HOME="$ISAAC/runtime-home/data" \
  "$ISAAC/python.sh" --no-ros-env "$AUDIT_DIR/revalidate_composed_usd_variants.py" \
  --staging "$STAGING" --output "$LOG" --experience "$EXP" \
  >"$LOG/stdout.log" 2>"$LOG/stderr.log"
rg -qx 'GT_ONLY_COMPOSED_VARIANT_REVALIDATION=PASS' "$LOG/stdout.log"
printf 'GT_ONLY_USD_VARIANT_REVALIDATION=PASS\n'
