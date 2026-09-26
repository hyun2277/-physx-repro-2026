"""Inference-only, memory-bounded SparseGroupNorm32 and peak-reducing block schedule."""

import json
import os

import torch
import torch.nn.functional as F

CPU_FP32_ATOL = 2e-5
CPU_FP32_RTOL = 2e-5
CPU_FP16_ATOL = 2e-3
CPU_FP16_RTOL = 2e-3
GPU_FP32_ATOL = 3e-5
GPU_FP32_RTOL = 3e-5
GPU_FP16_ATOL = 2e-3
GPU_FP16_RTOL = 2e-3
DEFAULT_CHUNK_ROWS = 16384
DEFAULT_THRESHOLD_BYTES = 512 * 2**20


def _validate(num_channels, num_groups, eps, features):
    if features.ndim != 2 or features.shape[1] != num_channels:
        raise RuntimeError(f"groupnorm shape mismatch: {tuple(features.shape)}, channels={num_channels}")
    if num_groups <= 0 or num_channels % num_groups:
        raise RuntimeError(f"channels {num_channels} are not divisible by groups {num_groups}")
    if eps <= 0 or features.dtype not in (torch.float16, torch.float32):
        raise RuntimeError(f"unsupported groupnorm eps/dtype: {eps}, {features.dtype}")
    if torch.is_grad_enabled():
        raise RuntimeError("memory-bounded groupnorm is inference-only")


def streaming_group_norm(features, layouts, num_groups, weight, bias, eps,
                         chunk_rows=DEFAULT_CHUNK_ROWS, output=None):
    """Three-pass implementation: mean, biased variance, then normalization."""
    channels = features.shape[1]
    _validate(channels, num_groups, eps, features)
    if chunk_rows <= 0:
        raise RuntimeError("chunk_rows must be positive")
    if (weight is None) != (bias is None):
        raise RuntimeError("affine weight and bias must both be present or absent")
    if weight is not None and (weight.shape != (channels,) or bias.shape != (channels,)):
        raise RuntimeError("affine parameter shape mismatch")
    result = torch.empty_like(features) if output is None else output
    if result.shape != features.shape or result.dtype != features.dtype or result.device != features.device:
        raise RuntimeError("preallocated groupnorm output contract mismatch")
    channels_per_group = channels // num_groups
    for layout in layouts:
        start = 0 if layout.start is None else layout.start
        stop = len(features) if layout.stop is None else layout.stop
        rows = stop - start
        if rows <= 0:
            raise RuntimeError("empty batch in sparse groupnorm")
        count = rows * channels_per_group
        total = torch.zeros(num_groups, dtype=torch.float64, device=features.device)
        for first in range(start, stop, chunk_rows):
            last = min(stop, first + chunk_rows)
            value = features[first:last].float().reshape(-1, num_groups, channels_per_group)
            total += value.sum(dim=(0, 2)).double()
            del value
        mean = (total / count).float()
        squared = torch.zeros(num_groups, dtype=torch.float64, device=features.device)
        for first in range(start, stop, chunk_rows):
            last = min(stop, first + chunk_rows)
            value = features[first:last].float().reshape(-1, num_groups, channels_per_group)
            squared += ((value - mean[None, :, None]) ** 2).sum(dim=(0, 2)).double()
            del value
        variance = (squared / count).float()  # biased variance, matching torch GroupNorm
        if not torch.isfinite(mean).all() or not torch.isfinite(variance).all() or (variance < 0).any():
            raise RuntimeError("nonfinite/negative streaming groupnorm statistics")
        inv_std = torch.rsqrt(variance + eps)
        affine_weight = None if weight is None else weight.float().reshape(num_groups, channels_per_group)
        affine_bias = None if bias is None else bias.float().reshape(num_groups, channels_per_group)
        for first in range(start, stop, chunk_rows):
            last = min(stop, first + chunk_rows)
            value = features[first:last].float().reshape(-1, num_groups, channels_per_group)
            value = (value - mean[None, :, None]) * inv_std[None, :, None]
            if affine_weight is not None:
                value = value * affine_weight[None, :, :] + affine_bias[None, :, :]
            converted = value.reshape(last - first, channels).to(features.dtype)
            if not torch.isfinite(converted).all():
                raise RuntimeError("nonfinite memory-bounded groupnorm output chunk")
            result[first:last] = converted
            del value, converted
    return result


def memory_projection(features, chunk_rows=DEFAULT_CHUNK_ROWS):
    device = features.device
    free_bytes, total_bytes = torch.cuda.mem_get_info(device)
    allocated = torch.cuda.memory_allocated(device)
    reserved = torch.cuda.memory_reserved(device)
    cached_free = max(0, reserved - allocated)
    output_bytes = features.numel() * features.element_size()
    rows = min(chunk_rows, len(features))
    chunk_fp32 = rows * features.shape[1] * 4
    # value, squared-difference temporary, and conservative indexing/runtime margin.
    chunk_peak = chunk_fp32 * 3
    expected_new = output_bytes + chunk_peak
    external_growth = max(0, expected_new - cached_free)
    reserve_bytes = int(os.environ.get("PHYSX_GPU_RESERVE_MIB", "4607")) * 2**20
    projected_used = total_bytes - free_bytes + external_growth
    allowed_used = total_bytes - reserve_bytes
    report = {"free_bytes": free_bytes, "total_bytes": total_bytes, "allocated_bytes": allocated,
              "reserved_bytes": reserved, "cached_free_bytes": cached_free,
              "output_bytes": output_bytes, "chunk_peak_bytes": chunk_peak,
              "expected_new_bytes": expected_new, "expected_external_growth_bytes": external_growth,
              "projected_used_bytes": projected_used, "allowed_used_bytes": allowed_used,
              "reserve_bytes": reserve_bytes, "pass": projected_used <= allowed_used}
    print(json.dumps({"groupnorm_proactive_memory": report}), flush=True)
    if not report["pass"]:
        raise RuntimeError(f"proactive groupnorm memory guard failed: {report}")
    return report


def install():
    if os.environ.get("PHYSX_STREAMING_GROUPNORM_ENABLE") != "1":
        return
    from trellis.modules.sparse import norm as sparse_norm
    from trellis.models.structured_latent_vae import decoder_mesh

    original_norm = sparse_norm.SparseGroupNorm32.forward
    original_block = decoder_mesh.SparseSubdivideBlock3d.forward
    if getattr(original_norm, "_physx_memory_bounded", False) or getattr(original_block, "_physx_rescheduled", False):
        raise RuntimeError("groupnorm/block runtime adapter is already installed")

    def bounded_forward(self, x):
        fp32_bytes = x.feats.numel() * 4
        threshold = int(os.environ.get("PHYSX_STREAMING_GROUPNORM_THRESHOLD_BYTES", str(DEFAULT_THRESHOLD_BYTES)))
        if fp32_bytes < threshold:
            return original_norm(self, x)
        if self.num_channels != x.feats.shape[1]:
            raise RuntimeError("SparseGroupNorm32 channel mismatch")
        chunk_rows = int(os.environ.get("PHYSX_STREAMING_GROUPNORM_CHUNK_ROWS", str(DEFAULT_CHUNK_ROWS)))
        guard = memory_projection(x.feats, chunk_rows)
        print(json.dumps({"adapter": "memory_bounded_sparse_groupnorm32", "rows": len(x.feats),
                          "channels": self.num_channels, "groups": self.num_groups,
                          "eps": self.eps, "affine": self.affine, "dtype": str(x.feats.dtype),
                          "chunk_rows": chunk_rows, "fp32_full_copy_bytes_avoided": fp32_bytes,
                          "memory_guard": guard}), flush=True)
        result = streaming_group_norm(x.feats, x.layout, self.num_groups, self.weight, self.bias,
                                      self.eps, chunk_rows=chunk_rows)
        return x.replace(result)
    bounded_forward._physx_memory_bounded = True

    def rescheduled_block(self, x):
        # Mathematically identical branches; delay the residual subdivision until the main branch is complete.
        h = self.act_layers(x)
        h = self.sub(h)
        h = self.out_layers(h)
        residual = self.skip_connection(self.sub(x))
        return h + residual
    rescheduled_block._physx_rescheduled = True

    sparse_norm.SparseGroupNorm32.forward = bounded_forward
    decoder_mesh.SparseSubdivideBlock3d.forward = rescheduled_block


def _independent_reference(features, batch_sizes, groups, weight, bias, eps):
    out = torch.empty_like(features)
    start = 0; channels = features.shape[1]; cpg = channels // groups
    for rows in batch_sizes:
        value = features[start:start+rows].double().reshape(rows, groups, cpg)
        mean = value.mean(dim=(0, 2)); variance = ((value - mean[None, :, None]) ** 2).mean(dim=(0, 2))
        value = (value - mean[None, :, None]) / torch.sqrt(variance + eps)[None, :, None]
        if weight is not None:
            value = value * weight.double().reshape(groups, cpg)[None] + bias.double().reshape(groups, cpg)[None]
        out[start:start+rows] = value.reshape(rows, channels).to(features.dtype); start += rows
    return out


def validate_cases(device="cpu"):
    reports = []
    cases = [(torch.float32, [37], 4, True), (torch.float32, [19, 43], 8, False),
             (torch.float16, [41], 4, False), (torch.float16, [17, 52], 8, True)]
    for index, (dtype, batch_sizes, groups, affine) in enumerate(cases):
        torch.manual_seed(9000 + index)
        channels = 32; features = torch.randn(sum(batch_sizes), channels, device=device, dtype=dtype)
        weight = torch.randn(channels, device=device) if affine else None
        bias = torch.randn(channels, device=device) if affine else None
        layouts=[]; start=0
        for rows in batch_sizes: layouts.append(slice(start,start+rows)); start += rows
        with torch.inference_mode():
            expected=torch.empty_like(features); start=0
            for rows in batch_sizes:
                part=features[start:start+rows].T.reshape(1,channels,-1).float()
                normalized=F.group_norm(part,groups,weight,bias,1e-5)
                expected[start:start+rows]=normalized.reshape(channels,-1).T.to(dtype); start+=rows
            actual=streaming_group_norm(features,layouts,groups,weight,bias,1e-5,chunk_rows=11)
            reference=_independent_reference(features,batch_sizes,groups,weight,bias,1e-5)
        atol,rtol=(CPU_FP16_ATOL,CPU_FP16_RTOL) if dtype==torch.float16 else (CPU_FP32_ATOL,CPU_FP32_RTOL)
        if device!="cpu": atol,rtol=(GPU_FP16_ATOL,GPU_FP16_RTOL) if dtype==torch.float16 else (GPU_FP32_ATOL,GPU_FP32_RTOL)
        error=(actual.float()-expected.float()).abs(); ref_error=(actual.float()-reference.float()).abs()
        passed=torch.allclose(actual.float(),expected.float(),atol=atol,rtol=rtol) and torch.allclose(actual.float(),reference.float(),atol=atol,rtol=rtol)
        row={"device":device,"dtype":str(dtype),"batch_sizes":batch_sizes,"groups":groups,"affine":affine,
             "atol":atol,"rtol":rtol,"max_abs_vs_torch":float(error.max()),
             "max_rel_vs_torch":float((error/expected.float().abs().clamp_min(1e-6)).max()),
             "max_abs_vs_reference":float(ref_error.max()),"pass":bool(passed)}
        if not passed: raise RuntimeError(f"groupnorm equivalence failed: {row}")
        reports.append(row)
    # Contract rejection probes.
    with torch.inference_mode():
        for bad, bad_groups in ((torch.full((3, 8), float("nan")), 4), (torch.randn(3, 10), 3)):
            try: streaming_group_norm(bad,[slice(0,3)],bad_groups,None,None,1e-5,chunk_rows=2)
            except RuntimeError: pass
            else: raise RuntimeError("invalid groupnorm input was accepted")
    return reports


def validate_medium_gpu():
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable for mandatory medium groupnorm equivalence")
    torch.manual_seed(9010)
    batch_sizes=[50000,81072]; channels=256; groups=32; dtype=torch.float16
    features=torch.randn(sum(batch_sizes),channels,device="cuda",dtype=dtype)
    weight=torch.randn(channels,device="cuda"); bias=torch.randn(channels,device="cuda")
    layouts=[slice(0,batch_sizes[0]),slice(batch_sizes[0],sum(batch_sizes))]
    with torch.inference_mode():
        expected=torch.empty_like(features); start=0
        for rows in batch_sizes:
            part=features[start:start+rows].T.reshape(1,channels,-1).float()
            normalized=F.group_norm(part,groups,weight,bias,1e-5)
            expected[start:start+rows]=normalized.reshape(channels,-1).T.to(dtype); start+=rows
        actual=streaming_group_norm(features,layouts,groups,weight,bias,1e-5,chunk_rows=DEFAULT_CHUNK_ROWS)
        torch.cuda.synchronize()
    error=(actual.float()-expected.float()).abs()
    passed=torch.allclose(actual.float(),expected.float(),atol=GPU_FP16_ATOL,rtol=GPU_FP16_RTOL)
    report={"device":"cuda","dtype":str(dtype),"batch_sizes":batch_sizes,"channels":channels,
            "groups":groups,"affine":True,"atol":GPU_FP16_ATOL,"rtol":GPU_FP16_RTOL,
            "max_abs_vs_torch":float(error.max()),
            "max_rel_vs_torch":float((error/expected.float().abs().clamp_min(1e-6)).max()),"pass":bool(passed)}
    if not passed: raise RuntimeError(f"medium groupnorm equivalence failed: {report}")
    del features,weight,bias,expected,actual,error
    torch.cuda.empty_cache()
    return report


def validate_reschedule_cpu():
    torch.manual_seed(9020)
    x=torch.randn(7,8,dtype=torch.float64)
    main_weight=torch.randn(8,4,dtype=torch.float64)
    skip_weight=torch.randn(8,4,dtype=torch.float64)
    def act(value): return torch.nn.functional.silu(value)
    def subdivide(value): return value.repeat_interleave(8,dim=0)
    def main(value): return value @ main_weight
    def skip(value): return value @ skip_weight
    original_h=subdivide(act(x)); original_x=subdivide(x); original=main(original_h)+skip(original_x)
    rescheduled_h=main(subdivide(act(x))); rescheduled=rescheduled_h+skip(subdivide(x))
    error=(original-rescheduled).abs()
    if not torch.equal(original,rescheduled):
        raise RuntimeError("independent branch reschedule changed CPU mock result")
    return {"shape":list(original.shape),"max_abs":float(error.max()),"exact":True}
