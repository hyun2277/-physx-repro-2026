#!/usr/bin/env bash
# No URDF is provided or converted. This checks app, empty stage, URDF extension enable, and public API only.
set -euo pipefail
ROOT=/home/minsujo/Desktop/SH/PHYSx
ISAAC_ROOT="$ROOT/tools/isaac-sim"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-host-single-gpu-importer"
LOG_DIR="$ROOT/logs/isaac-sim-importer-diagnosis/$RUN_ID"
WORK_DIR="$ROOT/staging/isaac-sim-importer-diagnosis-$RUN_ID"
RUNTIME_HOME="$ISAAC_ROOT/runtime-home"
mkdir -p "$LOG_DIR" "$WORK_DIR" "$RUNTIME_HOME/cache" "$RUNTIME_HOME/config" "$RUNTIME_HOME/data"
trap 'rm -f "$WORK_DIR"/smoke_*.py' EXIT
cat > "$WORK_DIR/common.py" <<'PY'
from isaacsim import SimulationApp

def launch():
    return SimulationApp({
        "headless": True,
        "active_gpu": 1,       # physical GPU index from nvidia-smi
        "physics_gpu": 1,
        "multi_gpu": False,
        "extra_args": [
            "--enable", "isaacsim.asset.importer.urdf",
            "--/renderer/multiGpu/enabled=false",
        ],
    })
PY
cat > "$WORK_DIR/smoke_basic.py" <<'PY'
from common import launch
app = launch()
try:
    app.update()
    print("PHYSX_SMOKE_BASIC_APP=PASS", flush=True)
finally:
    app.close()
PY
cat > "$WORK_DIR/smoke_stage.py" <<'PY'
from common import launch
app = launch()
try:
    import omni.usd
    ctx = omni.usd.get_context()
    ctx.new_stage()
    app.update()
    assert ctx.get_stage() is not None
    print("PHYSX_SMOKE_USD_STAGE=PASS", flush=True)
finally:
    app.close()
PY
cat > "$WORK_DIR/smoke_importer.py" <<'PY'
from common import launch
app = launch()
try:
    import omni.kit.app
    manager = omni.kit.app.get_app().get_extension_manager()
    if not manager.is_extension_enabled("isaacsim.asset.importer.urdf"):
        manager.set_extension_enabled_immediate("isaacsim.asset.importer.urdf", True)
    app.update()
    ext_id = manager.get_enabled_extension_id("isaacsim.asset.importer.urdf")
    assert ext_id
    print("PHYSX_SMOKE_URDF_ENABLE=PASS", flush=True)
    print("PHYSX_SMOKE_URDF_EXTENSION_ID=" + ext_id, flush=True)
    import isaacsim.asset.importer.urdf as urdf
    assert hasattr(urdf, "URDFImporter") and hasattr(urdf, "URDFImporterConfig")
    print("PHYSX_SMOKE_URDF_API=PASS", flush=True)
finally:
    app.close()
PY
printf '%s\n' 'active_gpu=1' 'physics_gpu=1' 'multi_gpu=false' 'renderer_multi_gpu=false' 'p2p=not_enabled_or_tested' 'cuda_visible_devices=unset' > "$LOG_DIR/policy.txt"
for name in basic stage importer; do
  set +e
  env -u CUDA_VISIBLE_DEVICES -u CONDA_PREFIX -u CONDA_DEFAULT_ENV \
    HOME="$RUNTIME_HOME" XDG_CACHE_HOME="$RUNTIME_HOME/cache" XDG_CONFIG_HOME="$RUNTIME_HOME/config" XDG_DATA_HOME="$RUNTIME_HOME/data" \
    "$ISAAC_ROOT/python.sh" "$WORK_DIR/smoke_${name}.py" > "$LOG_DIR/${name}.stdout.log" 2> "$LOG_DIR/${name}.stderr.log"
  rc=$?
  set -e
  marker="PHYSX_SMOKE_$(tr '[:lower:]' '[:upper:]' <<< "$name")"
  if ! rg -q '^PHYSX_SMOKE_.*=PASS$' "$LOG_DIR/${name}.stdout.log"; then
    rc=70
  fi
  printf '%s\n' "$rc" > "$LOG_DIR/${name}.exit_code.txt"
  if [[ "$rc" -ne 0 ]]; then
    printf 'FAILED step=%s log=%s\n' "$name" "$LOG_DIR" >&2
    exit "$rc"
  fi
done
printf 'PASS log=%s\n' "$LOG_DIR"
