#!/usr/bin/env bash
set -u

ROOT=/home/minsujo/Desktop/SH/PHYSx
TOOLKIT="$ROOT/toolchains/cuda-12.8.1"
PYTHON="$ROOT/envs/physxgen/bin/python"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN="$ROOT/logs/nvdiffrast-gcc12/$STAMP"
OVERLAY="$RUN/cuda-home"
BUILD="$RUN/torch-extensions"
mkdir -p "$RUN" "$OVERLAY/bin" "$BUILD"

ln -s "$TOOLKIT/bin/nvcc" "$OVERLAY/bin/nvcc"
ln -s "$TOOLKIT/bin/nvlink" "$OVERLAY/bin/nvlink"
ln -s "$TOOLKIT/bin/ptxas" "$OVERLAY/bin/ptxas"
ln -s "$TOOLKIT/bin/fatbinary" "$OVERLAY/bin/fatbinary"
ln -s "$TOOLKIT/nvvm/bin/cicc" "$OVERLAY/bin/cicc"
ln -s "$TOOLKIT/targets/x86_64-linux/include" "$OVERLAY/include"
ln -s "$TOOLKIT/targets/x86_64-linux/lib" "$OVERLAY/lib"
ln -s "$TOOLKIT/targets/x86_64-linux/lib" "$OVERLAY/lib64"
ln -s "$TOOLKIT/targets/x86_64-linux" "$OVERLAY/targets"
ln -s "$TOOLKIT/nvvm" "$OVERLAY/nvvm"

export CC=/usr/bin/gcc-12
export CXX=/usr/bin/g++-12
export CUDAHOSTCXX=/usr/bin/g++-12
export NVCC_CCBIN=/usr/bin/g++-12
export CUDA_HOME="$OVERLAY"
export CUDACXX="$OVERLAY/bin/nvcc"
export PATH="$OVERLAY/bin:$PATH"
export TORCH_EXTENSIONS_DIR="$BUILD"
export TORCH_CUDA_ARCH_LIST=12.0
export CUDA_VISIBLE_DEVICES=

{
  echo "run=$RUN"
  echo "CUDA_HOME=$CUDA_HOME"
  echo "CUDACXX=$CUDACXX"
  echo "CC=$CC"
  echo "CXX=$CXX"
  echo "CUDAHOSTCXX=$CUDAHOSTCXX"
  echo "NVCC_CCBIN=$NVCC_CCBIN"
  echo "TORCH_EXTENSIONS_DIR=$TORCH_EXTENSIONS_DIR"
  echo "TORCH_CUDA_ARCH_LIST=$TORCH_CUDA_ARCH_LIST"
  echo "CUDA_VISIBLE_DEVICES=<empty>"
  echo "nvcc_resolved=$(readlink -f "$CUDACXX")"
  echo "gcc_resolved=$(readlink -f "$CC")"
  echo "g++_resolved=$(readlink -f "$CXX")"
  "$CUDACXX" --version
  "$CC" --version | head -1
  "$CXX" --version | head -1
  echo "host compiler selection: CC/CXX/CUDAHOSTCXX/NVCC_CCBIN explicitly set to GCC/G++ 12"
} >"$RUN/environment.log" 2>&1

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
