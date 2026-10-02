#!/usr/bin/env python3
"""Static audit without dependencies: only explicit dependency and GPU policy lines."""
import json
import re
from pathlib import Path

here = Path(__file__).resolve().parent
files = [here / "isaac_minimal_usd_physx.kit", here / "isaac_minimal_urdf_importer.kit"]
result = {}
for path in files:
    text = path.read_text(encoding="utf-8")
    deps = re.findall(r'^"([^"]+)"\s*=\s*\{\}', text, flags=re.MULTILINE)
    forbidden = [name for name in deps if "ml" in name.lower() or "ros" in name.lower()]
    if forbidden:
        raise SystemExit(f"forbidden explicit dependency in {path.name}: {forbidden}")
    if "omni.kit.usd.layers" not in deps:
        raise SystemExit(f"SimulationApp USD-layers dependency missing: {path.name}")
    if "renderer.multiGpu.enabled = false" not in text or "renderer.multiGpu.autoEnable = false" not in text:
        raise SystemExit(f"single-GPU renderer policy missing: {path.name}")
    result[path.name] = sorted(deps)
print(json.dumps({"status": "PASS", "experiences": result}, indent=2, ensure_ascii=False))
