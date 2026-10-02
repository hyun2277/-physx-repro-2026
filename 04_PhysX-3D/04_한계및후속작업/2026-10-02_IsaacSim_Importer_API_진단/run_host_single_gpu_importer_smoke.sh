#!/usr/bin/env bash
# No URDF is provided or converted. Four marker-gated smoke checks only.
set -euo pipefail
ROOT=/home/minsujo/Desktop/SH/PHYSx
REPO="$ROOT/repro-records"
DIAG="$REPO/04_PhysX-3D/04_한계및후속작업/2026-10-02_IsaacSim_Importer_API_진단"
ISAAC_ROOT="$ROOT/tools/isaac-sim"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-host-minimal-importer"
LOG_DIR="$ROOT/logs/isaac-sim-importer-diagnosis/$RUN_ID"
WORK_DIR="$ROOT/staging/isaac-sim-importer-diagnosis-$RUN_ID"
RUNTIME_HOME="$ISAAC_ROOT/runtime-home"
mkdir -p "$LOG_DIR" "$WORK_DIR" "$RUNTIME_HOME/cache" "$RUNTIME_HOME/config" "$RUNTIME_HOME/data"
trap 'rm -f "$WORK_DIR"/smoke_*.py "$WORK_DIR"/common.py' EXIT
"$DIAG/verify_minimal_experience.py" > "$LOG_DIR/static_experience_audit.json"
cat > "$WORK_DIR/common.py" <<PY
from isaacsim import SimulationApp
BASIC_EXPERIENCE = r"$DIAG/isaac_minimal_usd_physx.kit"
IMPORTER_EXPERIENCE = r"$DIAG/isaac_minimal_urdf_importer.kit"
def launch(experience):
    return SimulationApp({
        "headless": True,
        "active_gpu": 1,
        "physics_gpu": 1,
        "multi_gpu": False,
        "extra_args": [
            "--/renderer/multiGpu/enabled=false",
            "--/renderer/multiGpu/autoEnable=false",
        ],
    }, experience=experience)
PY
cat > "$WORK_DIR/smoke_app.py" <<'PY'
from common import BASIC_EXPERIENCE, launch
app = launch(BASIC_EXPERIENCE)
try:
    app.update()
    print("PHYSX_SMOKE_APP=PASS", flush=True)
finally:
    app.close()
PY
cat > "$WORK_DIR/smoke_stage.py" <<'PY'
from common import BASIC_EXPERIENCE, launch
app = launch(BASIC_EXPERIENCE)
try:
    import omni.usd
    ctx = omni.usd.get_context()
    ctx.new_stage()
    app.update()
    assert ctx.get_stage() is not None
    print("PHYSX_SMOKE_STAGE=PASS", flush=True)
finally:
    app.close()
PY
cat > "$WORK_DIR/smoke_enable.py" <<'PY'
from common import IMPORTER_EXPERIENCE, launch
app = launch(IMPORTER_EXPERIENCE)
try:
    import omni.kit.app
    manager = omni.kit.app.get_app().get_extension_manager()
    ext_id = manager.get_enabled_extension_id("isaacsim.asset.importer.urdf")
    assert ext_id
    print("PHYSX_SMOKE_IMPORTER_ENABLE=PASS", flush=True)
    print("PHYSX_SMOKE_IMPORTER_EXTENSION_ID=" + ext_id, flush=True)
finally:
    app.close()
PY
cat > "$WORK_DIR/smoke_api.py" <<'PY'
from common import IMPORTER_EXPERIENCE, launch
app = launch(IMPORTER_EXPERIENCE)
try:
    import isaacsim.asset.importer.urdf as urdf
    config = urdf.URDFImporterConfig()
    assert config is not None and hasattr(urdf, "URDFImporter")
    print("PHYSX_SMOKE_IMPORTER_API=PASS", flush=True)
finally:
    app.close()
PY
printf '%s\n' 'active_gpu=1' 'physics_gpu=1' 'multi_gpu=false' 'renderer_multi_gpu=false' 'p2p=not_enabled_or_tested' 'cuda_visible_devices=unset' > "$LOG_DIR/policy.txt"
for step in app stage enable api; do
  case "$step" in
    app) marker='PHYSX_SMOKE_APP=PASS' ;;
    stage) marker='PHYSX_SMOKE_STAGE=PASS' ;;
    enable) marker='PHYSX_SMOKE_IMPORTER_ENABLE=PASS' ;;
    api) marker='PHYSX_SMOKE_IMPORTER_API=PASS' ;;
  esac
  set +e
  env -u CUDA_VISIBLE_DEVICES -u CONDA_PREFIX -u CONDA_DEFAULT_ENV \
    HOME="$RUNTIME_HOME" XDG_CACHE_HOME="$RUNTIME_HOME/cache" XDG_CONFIG_HOME="$RUNTIME_HOME/config" XDG_DATA_HOME="$RUNTIME_HOME/data" \
    "$ISAAC_ROOT/python.sh" "$WORK_DIR/smoke_${step}.py" > "$LOG_DIR/${step}.stdout.log" 2> "$LOG_DIR/${step}.stderr.log"
  process_rc=$?
  set -e
  result_rc=$process_rc
  if ! rg -qx "$marker" "$LOG_DIR/${step}.stdout.log"; then result_rc=70; fi
  printf '%s\n' "$process_rc" > "$LOG_DIR/${step}.process_exit_code.txt"
  printf '%s\n' "$result_rc" > "$LOG_DIR/${step}.result_exit_code.txt"
  if [[ "$result_rc" -ne 0 ]]; then
    printf 'FAILED step=%s process_exit=%s result_exit=%s log=%s\n' "$step" "$process_rc" "$result_rc" "$LOG_DIR" >&2
    exit "$result_rc"
  fi
done
printf 'PASS log=%s\n' "$LOG_DIR"
