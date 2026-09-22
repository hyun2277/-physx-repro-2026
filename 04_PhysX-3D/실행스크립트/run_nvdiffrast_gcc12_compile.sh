#!/usr/bin/env bash
set -u

ROOT=/home/minsujo/Desktop/SH/PHYSx
TOOLKIT="$ROOT/toolchains/cuda-12.8.1"
PYTHON="$ROOT/envs/physxgen/bin/python"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN="$ROOT/logs/nvdiffrast-gcc12/$STAMP"
mkdir -p "$RUN"
source "$SCRIPT_DIR/cuda_jit_environment.sh"
cuda_jit_prepare "$RUN" "$TOOLKIT" /usr/bin/gcc-12 /usr/bin/g++-12 || exit 1
cuda_jit_write_environment "$RUN/environment.log"
export CUDA_VISIBLE_DEVICES=

cat >"$RUN/build_nvdiffrast.py" <<'PY'
import os
from pathlib import Path
import torch
from torch.utils.cpp_extension import load

pkg = Path(__import__('nvdiffrast').__file__).resolve().parent
torch_dir = pkg / 'torch'
sources = [
    pkg / 'common' / 'cudaraster' / 'impl' / 'Buffer.cpp',
    pkg / 'common' / 'cudaraster' / 'impl' / 'CudaRaster.cpp',
    pkg / 'common' / 'cudaraster' / 'impl' / 'RasterImpl.cu',
    pkg / 'common' / 'cudaraster' / 'impl' / 'RasterImpl.cpp',
    pkg / 'common' / 'common.cpp',
    pkg / 'common' / 'rasterize.cu',
    pkg / 'common' / 'interpolate.cu',
    pkg / 'common' / 'texture.cu',
    pkg / 'common' / 'texture.cpp',
    pkg / 'common' / 'antialias.cu',
    torch_dir / 'torch_bindings.cpp',
    torch_dir / 'torch_rasterize.cpp',
    torch_dir / 'torch_interpolate.cpp',
    torch_dir / 'torch_texture.cpp',
    torch_dir / 'torch_antialias.cpp',
]
common = ['-DNVDR_TORCH']
cuda = common + ['-lineinfo', '-gencode=arch=compute_120,code=sm_120']
print('nvdiffrast JIT source count:', len(sources), flush=True)
print('nvcc host selection env:', {k: os.environ.get(k) for k in ('CC', 'CXX', 'CUDAHOSTCXX', 'NVCC_CCBIN')}, flush=True)
load(name='nvdiffrast_plugin_gcc12_probe', sources=[str(x) for x in sources],
     extra_cflags=common, extra_cuda_cflags=cuda, with_cuda=True, verbose=True)
print('nvdiffrast JIT compile and load completed', flush=True)
PY

set +e
"$PYTHON" -B "$RUN/build_nvdiffrast.py" >"$RUN/build.stdout.log" 2>"$RUN/build.stderr.log"
rc=$?
set -e
printf '%s\n' "$rc" >"$RUN/exit_code.txt"
printf 'exit_code=%s\n' "$rc" >"$RUN/result.txt"
if [ "$rc" -eq 0 ]; then
  echo "GCC 12 nvdiffrast JIT compile succeeded; logs=$RUN"
else
  echo "GCC 12 nvdiffrast JIT compile failed (exit $rc); logs=$RUN"
fi
exit "$rc"
