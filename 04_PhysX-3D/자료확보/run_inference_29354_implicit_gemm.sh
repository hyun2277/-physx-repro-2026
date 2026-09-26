#!/usr/bin/env bash
set -u -o pipefail

ROOT=/home/minsujo/Desktop/SH/PHYSx
SRC="$ROOT/sources/physx-4f54e750a309"
PY="$ROOT/envs/physxgen/bin/python"
INPUT="$ROOT/staging/render-cond-29354-portable-20260925T185825Z/datasets/PhysXNet/renders_cond/29354_/000.png"
TRANSFORMS="${INPUT%000.png}transforms.json"
MANIFEST="$ROOT/repro-records/04_PhysX-3D/자료확보/evidence/29354-inference-checkpoint-manifest.txt"
CUDA_TOOLKIT="$ROOT/toolchains/cuda-12.8.1"
CUDA_ENV="$ROOT/repro-records/04_PhysX-3D/실행스크립트/cuda_jit_environment.sh"
EXPECTED_HEAD=4f54e750a309fe9cd9f20816916ecc0e8a9ae594
INPUT_SHA=2db40557423afe1f0e1ae4e85c72e702f25fee227931a564c92879c68f733e85
TRANSFORMS_SHA=636144e9fc74f41cb0160b2c877aa0e798e55d4fa0e466434cb16703d0a28a3d
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
RUN="$ROOT/logs/inference-29354-implicit-gemm/$RUN_ID"
STAGE="$ROOT/staging/inference-29354-implicit-gemm-$RUN_ID"
EXAMPLE_COPY="$STAGE/example.py"
OUT="$ROOT/staging/inference-29354-implicit-output-$RUN_ID"
SOURCE_PYTHONPATH="$SRC${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$RUN" "$STAGE" "$OUT"
cp "$SRC/example.py" "$EXAMPLE_COPY"
sed -i "s/os.environ\['SPCONV_ALGO'\] = 'native'/os.environ['SPCONV_ALGO'] = 'implicit_gemm'/" "$EXAMPLE_COPY"

abort() { echo "ABORT_REASON=$1" | tee "$RUN/abort_reason.txt"; echo 2 > "$RUN/exit_code.txt"; exit 2; }

{
  echo "run_id=$RUN_ID"
  echo "spconv_algo=implicit_gemm"
  echo "source_head=$(git -C "$SRC" rev-parse HEAD)"
  echo "expected_source_head=$EXPECTED_HEAD"
  echo "input=$INPUT"
  echo "transforms=$TRANSFORMS"
  echo "example_copy=$EXAMPLE_COPY"
  echo "output=$OUT"
  echo "source_pythonpath=$SOURCE_PYTHONPATH"
  echo "input_sha256=$(sha256sum "$INPUT" 2>/dev/null | awk '{print $1}')"
  echo "transforms_sha256=$(sha256sum "$TRANSFORMS" 2>/dev/null | awk '{print $1}')"
  echo 'unstaged_tracked:'
  git -C "$SRC" diff --name-status
  echo 'staged_tracked:'
  git -C "$SRC" diff --cached --name-status
  echo 'untracked_protected:'
  git -C "$SRC" status --short --untracked-files=all | awk '$1=="??" {print}'
} > "$RUN/preflight.log" 2>&1

[[ "$(git -C "$SRC" rev-parse HEAD)" == "$EXPECTED_HEAD" ]] || abort source_head_mismatch
[[ -f "$INPUT" && -f "$TRANSFORMS" ]] || abort conditioning_input_missing
[[ "$(sha256sum "$INPUT" | awk '{print $1}')" == "$INPUT_SHA" ]] || abort input_hash_mismatch
[[ "$(sha256sum "$TRANSFORMS" | awk '{print $1}')" == "$TRANSFORMS_SHA" ]] || abort transforms_hash_mismatch
"$PY" -B - "$SRC/example.py" "$EXAMPLE_COPY" "$RUN/example_diff.log" <<'PY'
import difflib, pathlib, sys
orig, copy, out = map(pathlib.Path, sys.argv[1:])
a, b = orig.read_text().splitlines(keepends=True), copy.read_text().splitlines(keepends=True)
if len(a) != len(b): raise SystemExit("line_count_changed")
changed = [i for i, (x, y) in enumerate(zip(a, b), 1) if x != y]
if changed != [3] or not a[2].startswith("os.environ['SPCONV_ALGO'] = 'native'") or not b[2].startswith("os.environ['SPCONV_ALGO'] = 'implicit_gemm'"):
    raise SystemExit(f"unexpected_diff={changed}")
out.write_text("".join(difflib.unified_diff(a, b, fromfile=str(orig), tofile=str(copy))))
print("diff_only_line=3")
PY

changed_paths() { { git -C "$SRC" diff --name-only; git -C "$SRC" diff --cached --name-only; } | sort -u; }
is_allowed_pyc() { [[ "$1" =~ ^trellis/(.*/)?__pycache__/[^/]+\.pyc$ ]]; }
mapfile -t changed < <(changed_paths)
bad=(); allowed=()
for path in "${changed[@]}"; do
  test -z "$path" && continue
  if is_allowed_pyc "$path"; then allowed+=("$path"); else bad+=("$path"); fi
done
printf 'allowed_pyc=%s\n' "${allowed[@]}" >> "$RUN/preflight.log"
echo "allowed_pyc_count=${#allowed[@]}" >> "$RUN/preflight.log"
printf 'remaining_change=%s\n' "${bad[@]}" >> "$RUN/preflight.log"
[[ "${#bad[@]}" -eq 0 ]] || abort non_pyc_tracked_source_change

while read -r expected rel; do
  test -z "$expected" && continue
  file="$SRC/$rel"
  [[ -f "$file" ]] || abort checkpoint_missing:$rel
  actual=$(sha256sum "$file" | awk '{print $1}')
  echo "$actual  $rel" >> "$RUN/checkpoint_hashes.txt"
  [[ "$actual" == "$expected" ]] || abort checkpoint_hash_mismatch:$rel
done < "$MANIFEST"

set +e
nvidia-smi --query-gpu=index,uuid --format=csv,noheader,nounits > "$RUN/gpu_index_uuid.log" 2>&1
GPU_RC=$?
set -e
[[ "$GPU_RC" -eq 0 ]] || abort nvidia_smi_unavailable
GPU1_UUID=$(awk -F',' '$1 ~ /^[[:space:]]*1[[:space:]]*$/ {gsub(/[[:space:]]/,"",$2); print $2}' "$RUN/gpu_index_uuid.log")
[[ -n "$GPU1_UUID" ]] || abort gpu1_uuid_missing
set +e
nvidia-smi --query-compute-apps=pid,gpu_uuid,used_memory --format=csv,noheader,nounits > "$RUN/gpu_compute_pre.log" 2>&1
APPS_RC=$?
set -e
[[ "$APPS_RC" -eq 0 ]] || abort gpu_compute_query_failed
if awk -F',' -v target="$GPU1_UUID" '{gsub(/[[:space:]]/,"",$2); if ($2==target) found=1} END{exit found?0:1}' "$RUN/gpu_compute_pre.log"; then abort gpu1_compute_process_present; fi

source "$CUDA_ENV" || abort cuda_environment_load_failed
cuda_jit_prepare "$RUN" "$CUDA_TOOLKIT" /usr/bin/gcc-12 /usr/bin/g++-12 || abort cuda_overlay_prepare_failed
cuda_jit_write_environment "$RUN/environment.log"
printf '%q ' env CUDA_VISIBLE_DEVICES=1 PYTHONPATH="$SOURCE_PYTHONPATH" CUDA_HOME="$CUDA_HOME" CUDACXX="$CUDACXX" CC="$CC" CXX="$CXX" CUDAHOSTCXX="$CUDAHOSTCXX" NVCC_CCBIN="$NVCC_CCBIN" PATH="$PATH" HOME="$SRC" XDG_CACHE_HOME="$ROOT/cache" "$PY" "$EXAMPLE_COPY" --condpath "$INPUT" --savepath "$OUT" > "$RUN/example.command.txt"
date -u +%Y-%m-%dT%H:%M:%SZ > "$RUN/start_utc.txt"
set +e
(cd "$SRC" && PYTHONUNBUFFERED=1 env CUDA_VISIBLE_DEVICES=1 PYTHONPATH="$SOURCE_PYTHONPATH" CUDA_HOME="$CUDA_HOME" CUDACXX="$CUDACXX" CC="$CC" CXX="$CXX" CUDAHOSTCXX="$CUDAHOSTCXX" NVCC_CCBIN="$NVCC_CCBIN" PATH="$PATH" HOME="$SRC" XDG_CACHE_HOME="$ROOT/cache" "$PY" "$EXAMPLE_COPY" --condpath "$INPUT" --savepath "$OUT") > "$RUN/example.stdout.log" 2> "$RUN/example.stderr.log" &
example_pid=$!
(
  while kill -0 "$example_pid" 2>/dev/null; do
    nvidia-smi --query-compute-apps=pid,gpu_uuid,used_memory --format=csv,noheader,nounits >> "$RUN/gpu_usage.log" 2>&1
    sleep 5
  done
) &
poll_pid=$!
wait "$example_pid"; RC=$?
set -e
kill "$poll_pid" 2>/dev/null || true
wait "$poll_pid" 2>/dev/null || true
date -u +%Y-%m-%dT%H:%M:%SZ > "$RUN/end_utc.txt"
echo "$RC" > "$RUN/example.exit_code.txt"
set +e
nvidia-smi --query-compute-apps=pid,gpu_uuid,used_memory --format=csv,noheader,nounits > "$RUN/gpu_compute_post.log" 2>&1
set -e
[[ "$RC" -eq 0 ]] || abort example_failed

RESULT="$OUT/pretrain/diffusion"
VERIFY_RC=0
{
  for f in rgb.mp4 affordance.mp4 material.mp4 description.mp4 texture.glb; do [[ -s "$RESULT/$f" ]] || { echo "missing_or_empty=$f"; VERIFY_RC=1; }; done
  for f in rgb.mp4 affordance.mp4 material.mp4 description.mp4; do ffprobe -v error -select_streams v:0 -count_frames -show_entries stream=nb_read_frames,width,height -of default=nw=1 "$RESULT/$f" || VERIFY_RC=1; done
  python3 - "$RESULT/texture.glb" <<'PY'
import pathlib, struct, sys
p=pathlib.Path(sys.argv[1]); b=p.read_bytes()
if len(b)<12 or b[:4]!=b'glTF' or struct.unpack_from('<I',b,4)[0]!=2: raise SystemExit('invalid GLB header')
print('glb_header=PASS bytes='+str(len(b)))
PY
} > "$RUN/output_verification.log" 2>&1
echo "$VERIFY_RC" > "$RUN/output_verification_exit_code.txt"
[[ "$VERIFY_RC" -eq 0 ]] || abort output_verification_failed
echo 0 > "$RUN/exit_code.txt"
