# Draft GitHub Issue: PhysX-3D inference on RTX 5090 hits spconv/cumm int32 limit

> This is a draft only. It has not been submitted.

## Environment

- PhysX-3D source: `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`
- Official setup script indicates PyTorch 2.4.0 + CUDA 11.8 and installs `spconv-cu118` (CUDA 11) or `spconv-cu120` (CUDA 12).
- Actual isolated environment: Python 3.10, `torch 2.7.1+cu128`, runtime CUDA 12.8, `spconv-cu126 2.3.8`, `cumm-cu126 0.7.11`.
- GPU: RTX 5090; execution restricted to GPU 1 with `CUDA_VISIBLE_DEVICES=1`.

## Reproduction

1. Use the official `example.py` and one existing conditioning image `renders_cond/29354_/000.png`.
2. Keep the pretrained checkpoint unchanged.
3. Run with CUDA 12.8 overlay and GCC 12.
4. Native run fails in `spconv.pytorch` `indice_subm_conv` with:

```text
int64_t(a.dim(0)) * int64_t(a.dim(1)) * tv::bit_size(algo_desp.dtype_a) / 8 < int_max assert faild. your data exceed int32 range.
```

The logged activation is `N=2168704`, `C=512`, fp16, so the checked byte product is `2220752896`, above `2147483647`.

For comparison, a staging copy changing only `SPCONV_ALGO` from `native` to `implicit_gemm` reaches `spconv.ops.implicit_gemm` and fails with the same assert and shape. Logs are available in the local reproduction record; no source or checkpoint was changed.

## Questions

1. Is there an official spconv/cumm release or commit that supports this large fp16 sparse GEMM shape through int64/NVRTC?
2. Which exact CUDA, torch, spconv, and cumm versions did the authors use for PhysX-3D inference?
3. Is RTX 5090/sm_120 supported by the released PhysX-3D setup, or should inference use an older GPU/CUDA stack?
4. Is reducing voxel/latent resolution expected to remain checkpoint-compatible, or would that be a different model?

No installation, source modification, or additional inference was performed while preparing this report.
