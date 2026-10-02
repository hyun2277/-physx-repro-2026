#!/usr/bin/env bash
set -euo pipefail

RECORD_DIR="/home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/04_한계및후속작업/2026-10-03_IsaacSim_GUI_USD_물리구동_시각검증"
export PHYSX_GUI_SETUP_SCRIPT="$RECORD_DIR/gui_10163_linked_clone_static.py"
echo "Static GUI only: linked presentation clones for 10163 GT-only USD; physics step count remains zero."
exec "$RECORD_DIR/run_gui_10163_gpu0_static.sh"
