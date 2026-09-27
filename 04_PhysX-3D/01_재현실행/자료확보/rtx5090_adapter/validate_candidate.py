"""CPU algebra and bounded GPU checks for the channel-tiled adapter."""

import argparse
import json
import os

INT32_MAX = 2**31 - 1
FP16_ATOL = 0.02
FP16_RTOL = 0.02


def boundary():
    n, channels, out_channels, bytes_per_value = 2168704, 512, 256, 2
    full = n * channels * bytes_per_value
    tile = n * 256 * bytes_per_value
    output = n * out_channels * bytes_per_value
    assert full == 2220752896 and full > INT32_MAX
    assert tile < INT32_MAX and output < INT32_MAX
    print(json.dumps(dict(full_bytes=full, tile_bytes=tile, output_bytes=output,
                          int32_max=INT32_MAX, pass_=True)))


def cpu():
    import torch
    torch.manual_seed(17)
    coords = [(x, y, z) for x in range(3) for y in range(3) for z in range(3)]
    # Drop two cells to exercise missing neighbours; retain boundary cells.
    coords.remove((0, 1, 1))
    coords.remove((2, 2, 0))
    features = torch.randn(len(coords), 64, dtype=torch.float64)
    weights = torch.randn(32, 3, 3, 3, 64, dtype=torch.float64)
    bias = torch.randn(32, dtype=torch.float64)
    index = {c: i for i, c in enumerate(coords)}

    def reference(parts):
        result = torch.zeros(len(coords), 32, dtype=torch.float64)
        for row, (x, y, z) in enumerate(coords):
            for kx in range(3):
                for ky in range(3):
                    for kz in range(3):
                        neighbour = (x + kx - 1, y + ky - 1, z + kz - 1)
                        if neighbour in index:
                            j = index[neighbour]
                            for first, last in parts:
                                result[row] += weights[:, kx, ky, kz, first:last] @ features[j, first:last]
        return result + bias

    whole = reference([(0, 64)])
    split = reference([(0, 32), (32, 64)])
    abs_error = (whole - split).abs()
    assert torch.allclose(whole, split, atol=1e-11, rtol=1e-11)
    print(json.dumps(dict(cpu_reference="pass", rows=len(coords), channels=64,
                          max_abs=float(abs_error.max()),
                          max_rel=float((abs_error / whole.abs().clamp_min(1e-12)).max()))))


def cpu_spconv():
    import torch
    import spconv.pytorch as spconv
    import channel_tiled_spconv as adapter
    torch.manual_seed(23)
    coords = torch.tensor([[0, x, y, z] for x in range(3) for y in range(3) for z in range(3)
                           if (x, y, z) not in ((0, 1, 1), (2, 2, 0))], dtype=torch.int32)
    features = torch.randn(len(coords), 64, dtype=torch.float32)
    sparse = spconv.SparseConvTensor(features, coords, [3, 3, 3], 1)
    # spconv's CPU backend rejects fused bias; GPU comparison exercises bias.
    conv = spconv.SubMConv3d(64, 32, 3, bias=False, indice_key='cpu_candidate',
                            algo=spconv.ConvAlgo.Native).eval()
    with torch.no_grad():
        original = adapter.ORIGINAL_FORWARD(conv, sparse)
        os.environ['PHYSX_TILE_TEST_FORCE'] = '1'
        try:
            tiled = adapter._tiled_forward(conv, sparse)
        finally:
            os.environ.pop('PHYSX_TILE_TEST_FORCE', None)
    assert torch.equal(original.indices, tiled.indices)
    lookup = {tuple(c): i for i, c in enumerate(coords.tolist())}
    reference = torch.zeros(len(coords), 32, dtype=torch.float64)
    weight = conv.weight.double()
    for row, (batch, x, y, z) in enumerate(coords.tolist()):
        for kx in range(3):
            for ky in range(3):
                for kz in range(3):
                    neighbour = (batch, x + kx - 1, y + ky - 1, z + kz - 1)
                    if neighbour in lookup:
                        reference[row] += weight[:, kx, ky, kz] @ features[lookup[neighbour]].double()
    abs_orig = (original.features.double() - tiled.features.double()).abs()
    abs_ref = (reference - tiled.features.double()).abs()
    assert torch.allclose(original.features, tiled.features, atol=1e-4, rtol=1e-4)
    assert torch.allclose(reference, tiled.features.double(), atol=1e-4, rtol=1e-4)
    print(json.dumps({'cpu_spconv': 'pass', 'rows': len(coords), 'in_channels': 64,
                      'out_channels': 32, 'max_abs_vs_spconv': float(abs_orig.max()),
                      'max_abs_vs_reference': float(abs_ref.max()),
                      'max_rel_vs_reference': float((abs_ref / reference.abs().clamp_min(1e-8)).max())}))


def gpu():
    import torch
    import spconv.pytorch as spconv
    import channel_tiled_spconv as adapter
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable")
    torch.manual_seed(17)
    coords = torch.tensor([[0, x, y, z] for x in range(3) for y in range(3) for z in range(3)
                           if (x, y, z) not in ((0, 1, 1), (2, 2, 0))],
                          dtype=torch.int32, device="cuda")
    features = torch.randn(len(coords), 512, dtype=torch.float16, device="cuda")
    sparse = spconv.SparseConvTensor(features, coords, [3, 3, 3], 1)
    conv = spconv.SubMConv3d(512, 256, 3, bias=True, indice_key="candidate_test",
                            algo=spconv.ConvAlgo.Native).cuda().half().eval()
    with torch.inference_mode():
        expected = adapter.ORIGINAL_FORWARD(conv, sparse)
        os.environ["PHYSX_TILE_TEST_FORCE"] = "1"
        os.environ["PHYSX_TILE_TEST_CHANNELS"] = "256"
        try:
            actual = adapter._tiled_forward(conv, sparse)
        finally:
            os.environ.pop("PHYSX_TILE_TEST_FORCE", None)
            os.environ.pop("PHYSX_TILE_TEST_CHANNELS", None)
        torch.cuda.synchronize()
    if not torch.equal(expected.indices, actual.indices):
        raise RuntimeError("coordinate order changed")
    error = (expected.features.float() - actual.features.float()).abs()
    scale = expected.features.float().abs().clamp_min(1e-3)
    close = torch.allclose(expected.features.float(), actual.features.float(),
                           atol=FP16_ATOL, rtol=FP16_RTOL)
    report = dict(dtype="float16", atol=FP16_ATOL, rtol=FP16_RTOL,
                  max_abs=float(error.max()), max_rel=float((error / scale).max()),
                  same_coordinates=True, finite=bool(torch.isfinite(actual.features).all()),
                  pass_=bool(close))
    # Independent sparse neighbourhood sum using the checkpoint's KRSC weight layout.
    cpu_coords = coords.cpu().tolist()
    cpu_features = features.float().cpu()
    cpu_weights = conv.weight.float().cpu()
    cpu_bias = conv.bias.float().cpu()
    lookup = {tuple(c): i for i, c in enumerate(cpu_coords)}
    reference = torch.zeros(len(coords), 256)
    for row, (batch, x, y, z) in enumerate(cpu_coords):
        for kx in range(3):
            for ky in range(3):
                for kz in range(3):
                    neighbour = (batch, x + kx - 1, y + ky - 1, z + kz - 1)
                    if neighbour in lookup:
                        reference[row] += cpu_weights[:, kx, ky, kz] @ cpu_features[lookup[neighbour]]
    reference += cpu_bias
    ref_error = (reference - actual.features.float().cpu()).abs()
    ref_close = torch.allclose(reference, actual.features.float().cpu(), atol=0.08, rtol=0.05)
    report.update(reference_atol=0.08, reference_rtol=0.05,
                  reference_max_abs=float(ref_error.max()),
                  reference_max_rel=float((ref_error / reference.abs().clamp_min(1e-3)).max()),
                  reference_pass=bool(ref_close))
    print(json.dumps(report))
    if not report["pass_"] or not report["finite"] or not report["reference_pass"]:
        raise RuntimeError("candidate failed original spconv comparison")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["cpu", "cpu_spconv", "boundary", "gpu"])
    args = parser.parse_args()
    globals()[args.stage]()
