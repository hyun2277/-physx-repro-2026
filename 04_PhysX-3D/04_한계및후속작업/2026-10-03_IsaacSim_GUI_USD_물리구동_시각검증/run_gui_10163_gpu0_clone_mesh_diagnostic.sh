#!/usr/bin/env bash
set -euo pipefail

RECORD_DIR="/home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/04_한계및후속작업/2026-10-03_IsaacSim_GUI_USD_물리구동_시각검증"
export PHYSX_GUI_DIAGNOSTIC_MATERIAL=clone
echo "Diagnostic: source topology copied to ordinary session-layer Mesh prims with a reference cube; source USD is unchanged."
exec "$RECORD_DIR/run_gui_10163_gpu0_static.sh"
