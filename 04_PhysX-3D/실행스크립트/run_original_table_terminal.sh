#!/usr/bin/env bash
# Run the unmodified PhysX-3D table example from a normal Linux terminal.
# This script never downloads, installs, pushes, or edits the source checkout.
set -uo pipefail

ROOT=/home/minsujo/Desktop/SH/PHYSx
SRC="$ROOT/sources/physx-4f54e750a309"
PYTHON="$ROOT/envs/physxgen/bin/python"
EXPECTED_HEAD=4f54e750a309fe9cd9f20816916ecc0e8a9ae594
INPUT="$SRC/example/table.png"
LOG_ROOT="$ROOT/logs/original-example-terminal"
CLIP_CACHE="$ROOT/cache/clip/ViT-L-14.pt"

mkdir -p "$LOG_ROOT"
while :; do
    RUN="$LOG_ROOT/$(date -u +%Y%m%dT%H%M%SZ)"
    if mkdir "$RUN" 2>/dev/null; then break; fi
    sleep 1
done
OUTPUT="$RUN/output"
mkdir -p "$OUTPUT"
printf '%s\n' "$(date -u +%FT%TZ)" > "$RUN/started_at.txt"
printf '%s\n' 'CUDA_VISIBLE_DEVICES=1' > "$RUN/cuda_visible_devices.txt"
printf '%s\n' "$EXPECTED_HEAD" > "$RUN/expected_source_head.txt"

run_logged() {
    local name="$1"; shift
    printf '%q ' "$@" > "$RUN/$name.command.txt"
    printf '\n' >> "$RUN/$name.command.txt"
    "$@" >"$RUN/$name.stdout.log" 2>"$RUN/$name.stderr.log"
    local rc=$?
    printf '%s\n' "$rc" > "$RUN/$name.exit_code.txt"
    return "$rc"
}
stop_with_failure() {
    local reason="$1"
    printf '%s\n' "$reason" > "$RUN/ABORT_REASON.txt"
    printf '%s\n' "$(date -u +%FT%TZ)" > "$RUN/ended_at.txt"
    exit 1
}

# The source checkout must be fixed and have no tracked modifications. An
# untracked pretrain/ directory is explicitly allowed and is inventoried below.
run_logged source_head git -C "$SRC" rev-parse HEAD || stop_with_failure source_head_check_failed
[[ "$(cat "$RUN/source_head.stdout.log")" == "$EXPECTED_HEAD" ]] || stop_with_failure source_head_mismatch
run_logged source_diff git -C "$SRC" diff --quiet || stop_with_failure tracked_source_diff_present
run_logged source_status git -C "$SRC" status --short --untracked-files=normal
printf '%s\n' 'untracked pretrain/ is retained; git clean is never run' > "$RUN/source_status_note.txt"

[[ -x "$PYTHON" ]] || stop_with_failure physxgen_python_missing
[[ -f "$INPUT" ]] || stop_with_failure table_input_missing
[[ -f "$CLIP_CACHE" ]] || stop_with_failure clip_checkpoint_missing
[[ -d "$SRC/pretrain/diffusion" ]] || stop_with_failure diffusion_checkpoint_directory_missing

# Hash the input, CLIP checkpoint, and every existing torch/safetensors model.
sha256sum "$INPUT" > "$RUN/input_sha256.txt"
{
    stat --format='%n\t%s' "$CLIP_CACHE"
    sha256sum "$CLIP_CACHE"
    find "$SRC/pretrain" -type f \( -name '*.pt' -o -name '*.safetensors' \) -print0 |
        sort -z | while IFS= read -r -d '' f; do
            stat --format='%n\t%s' "$f"
            sha256sum "$f"
        done
} > "$RUN/model_inventory.txt" 2>"$RUN/model_inventory.stderr.log"
model_rc=$?
printf '%s\n' "$model_rc" > "$RUN/model_inventory.exit_code.txt"
[[ "$model_rc" -eq 0 ]] || stop_with_failure model_inventory_failed

# Keep CLIP's default ~/.cache/clip lookup inside PHYSx without downloading.
RUNTIME_HOME="$RUN/runtime-home"
mkdir -p "$RUNTIME_HOME/.cache"
ln -s "$ROOT/cache/clip" "$RUNTIME_HOME/.cache/clip" 2>"$RUN/clip_cache_link.stderr.log" || stop_with_failure clip_cache_link_failed

# These are the only GPU preflight commands. GPU 0 may be busy; GPU 1 must have
# no compute process. The visible device is physical GPU 1, logical torch:0.
run_logged preflight_nvidia_smi nvidia-smi || stop_with_failure nvidia_smi_failed
run_logged preflight_gpu_index_uuid nvidia-smi --query-gpu=index,uuid --format=csv,noheader,nounits || stop_with_failure gpu_index_uuid_query_failed
run_logged preflight_compute_apps nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv,noheader,nounits || stop_with_failure compute_app_query_failed
gpu1_uuid=$(awk -F',' 'function trim(value) {gsub(/^[[:space:]]+|[[:space:]]+$/, "", value); return value} {index=trim($1); uuid=trim($2); if (index == "1") {print uuid; exit}}' "$RUN/preflight_gpu_index_uuid.stdout.log")
[[ -n "$gpu1_uuid" ]] || stop_with_failure gpu1_uuid_missing
printf '%s\n' "$gpu1_uuid" > "$RUN/gpu1_uuid.txt"
if awk -F', *' -v uuid="$gpu1_uuid" '$1 == uuid {found=1} END {exit found ? 0 : 1}' "$RUN/preflight_compute_apps.stdout.log"; then
    stop_with_failure gpu1_has_compute_process
fi

run_logged preflight_torch env HOME="$RUNTIME_HOME" XDG_CACHE_HOME="$ROOT/cache" CUDA_VISIBLE_DEVICES=1 "$PYTHON" -I -B -c 'import torch; assert torch.cuda.is_available(); assert torch.cuda.device_count() == 1; print("torch="+torch.__version__); print("logical_device="+str(torch.cuda.current_device())); print("device_name="+torch.cuda.get_device_name(0)); x=torch.ones((256,256),device="cuda"); y=x @ x; torch.cuda.synchronize(); print("matmul_sum="+str(float(y.sum().item())))' || stop_with_failure torch_cuda_preflight_failed

printf '%s\n' 'CUDA_VISIBLE_DEVICES=1' > "$RUN/example_environment.txt"
printf 'cd %q && ' "$SRC" > "$RUN/example.command.txt"
printf '%q ' env HOME="$RUNTIME_HOME" XDG_CACHE_HOME="$ROOT/cache" CUDA_VISIBLE_DEVICES=1 "$PYTHON" example.py --condpath "$INPUT" --savepath "$OUTPUT" >> "$RUN/example.command.txt"
printf '\n' >> "$RUN/example.command.txt"
printf '%s\n' "$(date -u +%FT%TZ)" > "$RUN/example_started_at.txt"
(cd "$SRC" && PYTHONUNBUFFERED=1 env HOME="$RUNTIME_HOME" XDG_CACHE_HOME="$ROOT/cache" CUDA_VISIBLE_DEVICES=1 "$PYTHON" example.py --condpath "$INPUT" --savepath "$OUTPUT") >"$RUN/example.stdout.log" 2>"$RUN/example.stderr.log" &
example_pid=$!
# Record usage while the one allowed example process runs. This monitor is
# observational and does not reset, kill, or otherwise control the GPU.
(
    while kill -0 "$example_pid" 2>/dev/null; do
        printf '%s\t' "$(date -u +%FT%TZ)"
        nvidia-smi --query-gpu=index,uuid,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits
        rc=$?
        printf 'nvidia_smi_rc=%s\n' "$rc"
        sleep 2
    done
) > "$RUN/gpu_usage.log" 2>&1 &
monitor_pid=$!
wait "$example_pid"
example_rc=$?
printf '%s\n' "$example_rc" > "$RUN/example.exit_code.txt"
printf '%s\n' "$(date -u +%FT%TZ)" > "$RUN/example_ended_at.txt"
wait "$monitor_pid" 2>/dev/null || true

# Basic output existence and file-type inspection only; no metric evaluation.
find "$OUTPUT" -type f -printf '%P\t%s\n' | sort > "$RUN/output_files.txt"
: > "$RUN/output_file_types.txt"
while IFS= read -r rel; do
    file "$OUTPUT/$rel" >> "$RUN/output_file_types.txt" 2>&1 || true
done < <(find "$OUTPUT" -type f -printf '%P\n' | sort)
for expected in rgb.mp4 affordance.mp4 material.mp4 description.mp4 texture.glb kinematic.obj; do
    if find "$OUTPUT" -type f -name "$expected" -print -quit | grep -q .; then
        printf '%s\tpresent\n' "$expected"
    else
        printf '%s\tabsent\n' "$expected"
    fi
done > "$RUN/expected_outputs.txt"
printf '%s\n' "$(date -u +%FT%TZ)" > "$RUN/ended_at.txt"
# Return the official example's exit code; inspection never changes it.
exit "$example_rc"
