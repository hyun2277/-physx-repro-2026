#!/usr/bin/env bash
set -euo pipefail

RECORD_DIR="/home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/04_한계및후속작업/2026-10-03_IsaacSim_GUI_USD_물리구동_시각검증"
export PHYSX_GUI_DIAGNOSTIC_MATERIAL=solid
echo "Diagnostic: opaque solid material in anonymous session layer only; source USD is unchanged."
exec "$RECORD_DIR/run_gui_10163_gpu0_static.sh"
