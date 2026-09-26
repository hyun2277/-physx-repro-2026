#!/usr/bin/env python3
"""Mandatory small GPU equivalence suite before a cached decoder run."""
import json
import torch
import output_channel_tiled_spconv as output_adapter
import memory_bounded_groupnorm as groupnorm_adapter

if not torch.cuda.is_available(): raise RuntimeError("CUDA unavailable")
report = {
    "output_channel_tiling": output_adapter.validate_small_gpu(),
    "groupnorm_small": groupnorm_adapter.validate_cases("cuda"),
    "groupnorm_medium": groupnorm_adapter.validate_medium_gpu(),
    "groupnorm_reschedule_cpu": groupnorm_adapter.validate_reschedule_cpu(),
}
print(json.dumps(report), flush=True)
