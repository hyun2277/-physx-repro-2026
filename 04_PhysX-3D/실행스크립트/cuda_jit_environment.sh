#!/usr/bin/env bash

# Shared, per-run CUDA JIT environment. Source this file; do not execute it.
# Arguments to cuda_jit_prepare: run-dir toolkit-root host-cc host-cxx.
cuda_jit_prepare() {
    local run_dir="$1"
    local toolkit_root="$2"
    local host_cc="$3"
    local host_cxx="$4"
    local target="$toolkit_root/targets/x86_64-linux"
    local overlay="$run_dir/cuda-home"

    [[ -x "$toolkit_root/bin/nvcc" ]] || return 1
    [[ -x "$host_cc" && -x "$host_cxx" ]] || return 1
    [[ -d "$target/include" && -d "$target/lib" ]] || return 1

    mkdir -p "$overlay/bin" "$run_dir/torch-extensions" || return 1
    ln -s "$toolkit_root/bin/nvcc" "$overlay/bin/nvcc" || return 1
    ln -s "$toolkit_root/bin/nvlink" "$overlay/bin/nvlink" || return 1
    ln -s "$toolkit_root/bin/ptxas" "$overlay/bin/ptxas" || return 1
    ln -s "$toolkit_root/bin/fatbinary" "$overlay/bin/fatbinary" || return 1
    ln -s "$toolkit_root/nvvm/bin/cicc" "$overlay/bin/cicc" || return 1
    ln -s "$target/include" "$overlay/include" || return 1
    ln -s "$target/lib" "$overlay/lib" || return 1
    ln -s "$target/lib" "$overlay/lib64" || return 1
    ln -s "$target" "$overlay/targets" || return 1
    ln -s "$toolkit_root/nvvm" "$overlay/nvvm" || return 1

    export CUDA_HOME="$overlay"
    export CUDACXX="$overlay/bin/nvcc"
    export CC="$host_cc"
    export CXX="$host_cxx"
    export CUDAHOSTCXX="$host_cxx"
    export NVCC_CCBIN="$host_cxx"
    export TORCH_EXTENSIONS_DIR="$run_dir/torch-extensions"
    export TORCH_CUDA_ARCH_LIST=12.0
    export PATH="$overlay/bin:$PATH"
    CUDA_JIT_TOOLKIT_ROOT="$toolkit_root"
    CUDA_JIT_TARGET="$target"
    CUDA_JIT_OVERLAY="$overlay"
    CUDA_JIT_HOST_CC="$host_cc"
    CUDA_JIT_HOST_CXX="$host_cxx"
    export CUDA_JIT_TOOLKIT_ROOT CUDA_JIT_TARGET CUDA_JIT_OVERLAY CUDA_JIT_HOST_CC CUDA_JIT_HOST_CXX
}

cuda_jit_write_environment() {
    local output="$1"
    {
        printf 'CUDA_TOOLKIT_ROOT=%s\n' "$CUDA_JIT_TOOLKIT_ROOT"
        printf 'CUDA_HOME=%s\n' "$CUDA_HOME"
        printf 'CUDACXX=%s\n' "$CUDACXX"
        printf 'CC=%s\n' "$CC"
        printf 'CXX=%s\n' "$CXX"
        printf 'CUDAHOSTCXX=%s\n' "$CUDAHOSTCXX"
        printf 'NVCC_CCBIN=%s\n' "$NVCC_CCBIN"
        printf 'TORCH_EXTENSIONS_DIR=%s\n' "$TORCH_EXTENSIONS_DIR"
        printf 'TORCH_CUDA_ARCH_LIST=%s\n' "$TORCH_CUDA_ARCH_LIST"
        printf 'CC_RESOLVED=%s\n' "$(readlink -f "$CC")"
        printf 'CXX_RESOLVED=%s\n' "$(readlink -f "$CXX")"
        printf 'CUDA_TARGET_INCLUDE=%s\n' "$CUDA_JIT_TARGET/include"
        printf 'CUDA_TARGET_LIB=%s\n' "$CUDA_JIT_TARGET/lib"
        printf 'CUDA_TARGET_LIB64=%s\n' "$CUDA_JIT_TARGET/lib"
        printf 'overlay_links:\n'
        for link in bin/nvcc bin/cicc bin/nvlink bin/ptxas bin/fatbinary include lib lib64 nvvm targets; do
            printf '%s -> %s (resolved=%s)\n' "$CUDA_HOME/$link" "$(readlink "$CUDA_HOME/$link")" "$(readlink -f "$CUDA_HOME/$link")"
        done
        printf 'nvcc_version:\n'
        "$CUDACXX" --version
        printf 'host_cc_version:\n'
        "$CC" --version | head -1
        printf 'host_cxx_version:\n'
        "$CXX" --version | head -1
    } > "$output" 2>&1
}
