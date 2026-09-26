"""Opt-in, inference-only channel tiling for oversized native SubMConv3d.

The original checkpoint parameters and sparse coordinates are never changed.
GPU equivalence is a mandatory runner gate before a model run.
"""

import json
import os

import torch
import spconv.pytorch as spconv
from spconv.pytorch.conv import SparseConvolution, tv

INT32_MAX = 2**31 - 1
ORIGINAL_FORWARD = SparseConvolution.forward


def _tiled_forward(self, sparse_input, add_input=None):
    features = sparse_input.features
    n, channels = features.shape
    if n * channels * features.element_size() < INT32_MAX and os.environ.get("PHYSX_TILE_TEST_FORCE") != "1":
        return ORIGINAL_FORWARD(self, sparse_input, add_input)
    if not isinstance(self, spconv.SubMConv3d) or self.algo != spconv.ConvAlgo.Native:
        raise RuntimeError("oversized sparse operation is outside validated SubMConv3d Native scope")
    if self.training or torch.is_grad_enabled() or add_input is not None:
        raise RuntimeError("channel tiling is inference-only, without fused add")
    if self.groups != 1 or self.in_channels != channels or self.weight.shape != (
        self.out_channels, *self.kernel_size, channels
    ):
        raise RuntimeError("unsupported groups or weight layout")
    if n * self.out_channels * features.element_size() >= INT32_MAX:
        raise RuntimeError("output itself exceeds the int32 boundary")
    if self.act_type != tv.gemm.Activation.None_:
        raise RuntimeError("fused activation is unsupported by channel tiling")

    limit = (INT32_MAX - 1) // (n * features.element_size())
    tile_channels = min(256, (limit // 32) * 32)
    if os.environ.get("PHYSX_TILE_TEST_FORCE") == "1":
        tile_channels = min(tile_channels, int(os.environ.get("PHYSX_TILE_TEST_CHANNELS", "32")))
    if tile_channels < 32:
        raise RuntimeError("no safe multiple-of-32 input channel tile")
    coords_cpu = sparse_input.indices.cpu()
    unique_rows = len(torch.unique(coords_cpu, dim=0))
    if unique_rows != n:
        raise RuntimeError("duplicate sparse coordinates at oversized layer")
    print(json.dumps({"adapter": "channel_tiled_subm", "N": n, "C": channels,
                      "O": self.out_channels, "dtype": str(features.dtype),
                      "tile_channels": tile_channels, "indice_key": self.indice_key,
                      "coordinate_min": coords_cpu.min(dim=0).values.tolist(),
                      "coordinate_max": coords_cpu.max(dim=0).values.tolist(),
                      "duplicate_rows": n - unique_rows}), flush=True)
    accumulator = None
    for first in range(0, channels, tile_channels):
        last = min(channels, first + tile_channels)
        tile = spconv.SubMConv3d(
            last - first, self.out_channels, self.kernel_size,
            stride=self.stride, padding=self.padding, dilation=self.dilation,
            groups=1, bias=False, indice_key=self.indice_key, algo=self.algo,
            fp32_accum=self.fp32_accum,
        ).to(device=features.device, dtype=self.weight.dtype).eval()
        tile.weight = torch.nn.Parameter(self.weight[..., first:last].contiguous(), requires_grad=False)
        tile_input = sparse_input.replace_feature(features[:, first:last].contiguous())
        part = ORIGINAL_FORWARD(tile, tile_input)
        if not torch.equal(part.indices, sparse_input.indices):
            raise RuntimeError("tile changed sparse coordinate order")
        accumulator = part.features.float() if accumulator is None else accumulator + part.features.float()
    if self.bias is not None:
        accumulator = accumulator + self.bias.float()
    result = accumulator.to(features.dtype)
    if not torch.isfinite(result).all().item():
        raise RuntimeError("nonfinite tiled sparse output")
    return sparse_input.replace_feature(result)


def install():
    if os.environ.get("PHYSX_TILE_ENABLE") != "1":
        return
    if SparseConvolution.forward is not ORIGINAL_FORWARD:
        raise RuntimeError("another SparseConvolution patch is already active")
    SparseConvolution.forward = _tiled_forward
