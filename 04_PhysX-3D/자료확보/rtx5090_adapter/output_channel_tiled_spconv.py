"""Opt-in output-channel extension for oversized Native SubMConv3d outputs.

The established input-channel adapter remains responsible for operations whose
output fits the int32 byte boundary. This extension handles only the additional
case where the complete output exceeds that boundary. Each spconv call stays
below the boundary; output columns are concatenated in their original order.
"""

import json
import os

import torch
import spconv.pytorch as spconv
from spconv.pytorch.conv import SparseConvolution, tv

import channel_tiled_spconv as input_adapter

INT32_MAX = 2**31 - 1
FORWARD_BEFORE_OUTPUT_EXTENSION = SparseConvolution.forward


def _output_tiled_forward(self, sparse_input, add_input=None):
    features = sparse_input.features
    n, channels = features.shape
    output_bytes = n * self.out_channels * features.element_size()
    forced = os.environ.get("PHYSX_OUTPUT_TILE_TEST_FORCE") == "1"
    if output_bytes < INT32_MAX and not forced:
        return FORWARD_BEFORE_OUTPUT_EXTENSION(self, sparse_input, add_input)
    if not isinstance(self, spconv.SubMConv3d) or self.algo != spconv.ConvAlgo.Native:
        raise RuntimeError("oversized output is outside validated SubMConv3d Native scope")
    if self.training or torch.is_grad_enabled() or add_input is not None:
        raise RuntimeError("output tiling is inference-only, without fused add")
    if self.groups != 1 or self.in_channels != channels or self.weight.shape != (
        self.out_channels, *self.kernel_size, channels
    ):
        raise RuntimeError("unsupported groups or weight layout for output tiling")
    if self.act_type != tv.gemm.Activation.None_:
        raise RuntimeError("fused activation is unsupported by output tiling")

    input_limit = (INT32_MAX - 1) // (n * features.element_size())
    input_tile = min(256, (input_limit // 32) * 32)
    # Partial sums use float32, so bound those allocations as well as fp16 spconv outputs.
    output_limit = (INT32_MAX - 1) // (n * max(features.element_size(), 4))
    output_tile = min(self.out_channels, (output_limit // 32) * 32)
    if forced:
        input_tile = min(input_tile, int(os.environ.get("PHYSX_OUTPUT_TILE_TEST_INPUT_CHANNELS", "32")))
        output_tile = min(output_tile, int(os.environ.get("PHYSX_OUTPUT_TILE_TEST_OUTPUT_CHANNELS", "16")))
    if input_tile < 32 or output_tile < 32 and not forced:
        raise RuntimeError("no safe multiple-of-32 input/output tile")
    if forced and (input_tile < 1 or output_tile < 1):
        raise RuntimeError("invalid forced input/output tile")

    coords_cpu = sparse_input.indices.cpu()
    unique_rows = len(torch.unique(coords_cpu, dim=0))
    if unique_rows != n:
        raise RuntimeError("duplicate sparse coordinates at output-tiled layer")
    print(json.dumps({
        "adapter": "input_output_channel_tiled_subm", "N": n, "C": channels,
        "O": self.out_channels, "dtype": str(features.dtype),
        "input_tile_channels": input_tile, "output_tile_channels": output_tile,
        "input_bytes": n * channels * features.element_size(), "output_bytes": output_bytes,
        "float32_partial_bytes": n * output_tile * 4, "indice_key": self.indice_key,
        "coordinate_min": coords_cpu.min(0).values.tolist(),
        "coordinate_max": coords_cpu.max(0).values.tolist(), "duplicate_rows": n - unique_rows,
    }), flush=True)

    result = torch.empty((n, self.out_channels), device=features.device, dtype=features.dtype)
    for output_first in range(0, self.out_channels, output_tile):
        output_last = min(self.out_channels, output_first + output_tile)
        accumulator = None
        for input_first in range(0, channels, input_tile):
            input_last = min(channels, input_first + input_tile)
            tile = spconv.SubMConv3d(
                input_last - input_first, output_last - output_first, self.kernel_size,
                stride=self.stride, padding=self.padding, dilation=self.dilation,
                groups=1, bias=False, indice_key=self.indice_key, algo=self.algo,
                fp32_accum=self.fp32_accum,
            ).to(device=features.device, dtype=self.weight.dtype).eval()
            tile.weight = torch.nn.Parameter(
                self.weight[output_first:output_last, ..., input_first:input_last].contiguous(),
                requires_grad=False)
            tile_input = sparse_input.replace_feature(features[:, input_first:input_last].contiguous())
            part = input_adapter.ORIGINAL_FORWARD(tile, tile_input)
            if not torch.equal(part.indices, sparse_input.indices):
                raise RuntimeError("output tile changed sparse coordinate order")
            accumulator = part.features.float() if accumulator is None else accumulator + part.features.float()
            del part, tile_input, tile
        if self.bias is not None:
            accumulator = accumulator + self.bias[output_first:output_last].float()
        converted = accumulator.to(features.dtype)
        for row_first in range(0, n, 16384):
            row_last = min(n, row_first + 16384)
            if not torch.isfinite(converted[row_first:row_last]).all().item():
                raise RuntimeError("nonfinite output-tiled result chunk")
            result[row_first:row_last, output_first:output_last] = converted[row_first:row_last]
        del accumulator, converted
    if result.shape != (n, self.out_channels):
        raise RuntimeError(f"invalid output-tiled result: {tuple(result.shape)}")
    return sparse_input.replace_feature(result)


def install():
    if os.environ.get("PHYSX_OUTPUT_TILE_ENABLE") != "1":
        return
    if SparseConvolution.forward is not input_adapter._tiled_forward:
        raise RuntimeError("validated input-channel adapter must be installed first")
    SparseConvolution.forward = _output_tiled_forward


def validate_small_gpu():
    """Compare output tiling with original spconv and an independent neighbourhood sum."""
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable for mandatory output-tiling equivalence")
    cpu_rng = torch.get_rng_state()
    cuda_rng = torch.cuda.get_rng_state_all()
    try:
        torch.manual_seed(27281)
        coords = torch.tensor([[0, x, y, z] for x in range(3) for y in range(3) for z in range(3)
                               if (x, y, z) not in ((0, 1, 1), (2, 2, 0))],
                              dtype=torch.int32, device="cuda")
        features = torch.randn(len(coords), 64, dtype=torch.float16, device="cuda")
        sparse = spconv.SparseConvTensor(features, coords, [3, 3, 3], 1)
        conv = spconv.SubMConv3d(64, 32, 3, bias=True, indice_key="output_tile_validation",
                                algo=spconv.ConvAlgo.Native).cuda().half().eval()
        with torch.inference_mode():
            expected = input_adapter.ORIGINAL_FORWARD(conv, sparse)
            os.environ["PHYSX_OUTPUT_TILE_TEST_FORCE"] = "1"
            os.environ["PHYSX_OUTPUT_TILE_TEST_INPUT_CHANNELS"] = "32"
            os.environ["PHYSX_OUTPUT_TILE_TEST_OUTPUT_CHANNELS"] = "16"
            try:
                actual = _output_tiled_forward(conv, sparse)
            finally:
                for key in ("PHYSX_OUTPUT_TILE_TEST_FORCE", "PHYSX_OUTPUT_TILE_TEST_INPUT_CHANNELS",
                            "PHYSX_OUTPUT_TILE_TEST_OUTPUT_CHANNELS"):
                    os.environ.pop(key, None)
            torch.cuda.synchronize()
        if not torch.equal(expected.indices, actual.indices):
            raise RuntimeError("small output-tile validation changed coordinate order")
        error = (expected.features.float() - actual.features.float()).abs()
        close = torch.allclose(expected.features.float(), actual.features.float(), atol=.02, rtol=.02)
        cpu_coords = coords.cpu().tolist(); cpu_features = features.float().cpu()
        weights = conv.weight.float().cpu(); bias = conv.bias.float().cpu()
        lookup = {tuple(c): i for i, c in enumerate(cpu_coords)}
        reference = torch.zeros(len(coords), 32)
        for row, (batch, x, y, z) in enumerate(cpu_coords):
            for kx in range(3):
                for ky in range(3):
                    for kz in range(3):
                        neighbour = (batch, x+kx-1, y+ky-1, z+kz-1)
                        if neighbour in lookup:
                            reference[row] += weights[:, kx, ky, kz] @ cpu_features[lookup[neighbour]]
        reference += bias
        ref_error = (reference - actual.features.float().cpu()).abs()
        ref_close = torch.allclose(reference, actual.features.float().cpu(), atol=.08, rtol=.05)
        report = {"original_close": bool(close), "reference_close": bool(ref_close),
                  "same_coordinates": True, "finite": bool(torch.isfinite(actual.features).all()),
                  "max_abs_vs_original": float(error.max()), "max_abs_vs_reference": float(ref_error.max()),
                  "atol": .02, "rtol": .02, "reference_atol": .08, "reference_rtol": .05}
        if not all(report[k] for k in ("original_close", "reference_close", "same_coordinates", "finite")):
            raise RuntimeError(f"output-channel tiling equivalence failed: {report}")
        return report
    finally:
        torch.set_rng_state(cpu_rng); torch.cuda.set_rng_state_all(cuda_rng)
        torch.cuda.empty_cache()


def validate_cpu_contract():
    n = 73024 * 8 * 8; out_channels = 256; element_size = 2
    full = n * out_channels * element_size
    output_tile = ((INT32_MAX - 1) // (n * 4) // 32) * 32
    if n != 4673536 or full != 2392850432 or full <= INT32_MAX or output_tile != 96:
        raise RuntimeError("27281 output boundary arithmetic changed")
    if n * output_tile * 4 >= INT32_MAX:
        raise RuntimeError("float32 partial output tile exceeds int32 boundary")
    return {"rows": n, "channels": out_channels, "fp16_output_bytes": full,
            "output_tile_channels": output_tile, "float32_partial_bytes": n * output_tile * 4,
            "int32_max": INT32_MAX}
