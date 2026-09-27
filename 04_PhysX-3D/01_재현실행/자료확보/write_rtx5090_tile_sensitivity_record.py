#!/usr/bin/env python3
"""Materialize a small, Git-safe record from one completed tile probe."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    run, out = a.run.resolve(), a.output.resolve()
    result = run / "sensitivity_result_recomputed_v2.json"
    if out.exists() or not result.is_file():
        raise RuntimeError("output must be new and recomputed result must exist")
    data = json.loads(result.read_text())
    out.mkdir(parents=True)
    shutil.copy2(result, out / "sensitivity_result.json")
    traces = {}
    for oid in data["samples"]:
        traces[oid] = {}
        for label in ("baseline_a", "baseline_b_control", "tile_128"):
            found = []
            for log in (run / "steps").glob(f"*_{oid}_{label}_*/stdout.log"):
                for line in log.read_text(errors="replace").splitlines():
                    if '"adapter": "channel_tiled_subm"' in line:
                        found.append(json.loads(line))
            traces[oid][label] = found
    manifest = {"run": str(run), "run_result_sha256": sha(run / "result.json"),
                "comparison_sha256": sha(result), "channel_tiled_native_trace": traces,
                "scope": "new tile-sensitivity outputs only; no prior 25-sample artifact was modified"}
    (out / "hash_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    lines = ["# RTX 5090 adapter tile sensitivity", "", "This is an adapter sensitivity probe, not a CUDA 11.8 comparison, a complete adapter-equivalence proof, or a PhysX-3D Table 2 reproduction.", "",
             "## Fixed conditions", "", "- Same saved conditioning `000.png`, checkpoints, seed 1, GPU 1, Native spconv, CUDA 12.8.1 overlay, GCC 12, output-channel tiling, streaming GroupNorm, and separated physics/mesh decoder children.",
             "- GPU monitor limit: 28,000 MiB; reserve: 4,607 MiB. Each physics and mesh child passed its proactive pre-allocation guard.",
             "- Configurations: baseline A = 256 input channels/tile; baseline B = independent 256 control; comparison = 128 input channels/tile.",
             "- Sampling itself shows CUDA repeat variation despite the same seed. Mesh topology can therefore differ and raw vertex rows are not compared after a vertex-count mismatch. Deterministic surface diagnostics, scale, and group diagnostics are retained separately.", "",
             "## Results", "", "| Object | 256 control vs baseline | 128 vs baseline | Native input tiling trace | Judgment |", "|---|---:|---:|---|---|"]
    for oid, sample in data["samples"].items():
        control = sample["comparisons"]["control_256_repeat"]["latent"]["per_tensor"]["phy_feats"]["relative_l2"]
        tiled = sample["comparisons"]["tile_128_vs_256"]["latent"]["per_tensor"]["phy_feats"]["relative_l2"]
        trace = traces[oid]
        trace_text = "256/128 observed" if trace["baseline_a"] and trace["tile_128"] else "not invoked for this input"
        lines.append(f"| {oid} | phy latent rel-L2 {control:.6g} | phy latent rel-L2 {tiled:.6g} | {trace_text} | `{sample['judgement']}` |")
    lines += ["", "## Semantic screen", ""]
    for oid, sample in data["samples"].items():
        a_cfg, b_cfg = sample["configs"]["baseline_a"], sample["configs"]["tile_128"]
        lines += [f"### {oid}", "", f"- Official group count: 256 = {a_cfg['official_group_diagnostic']['predicted_num_group']}; 128 = {b_cfg['official_group_diagnostic']['predicted_num_group']}.",
                  f"- Moving-group meaningful screen: 256 = {a_cfg['official_group_diagnostic']['moving_group_meaningful']}; 128 = {b_cfg['official_group_diagnostic']['moving_group_meaningful']}.",
                  f"- Predicted scale mean [cm]: 256 = {a_cfg['scale_mean_cm']:.8g}; 128 = {b_cfg['scale_mean_cm']:.8g}."]
        if oid == "29806":
            for label in ("baseline_a", "baseline_b_control", "tile_128"):
                audit_path = Path(sample["configs"][label]["paths"]["mesh"]).parent.parent / "audit/official_result.json"
                g = json.loads(audit_path.read_text())["groups"].get("1", {})
                lines.append(f"- {label} group 1: area={g.get('majority_area')}, area_fraction={g.get('majority_area_fraction')}, components={g.get('components', {}).get('count_including_isolated')}.")
    lines += ["", "`numerically_different_but_semantically_stable` means that the declared group-count and meaningful-moving-surface screen matched while floating-point/mesh outputs differed. It does not establish bitwise equality, full adapter fidelity, physical accuracy, or paper-level evaluation equivalence.",
              "", "The full small comparison record is `sensitivity_result.json`; all referenced large artifacts remain outside Git."]
    (out / "README.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"output": str(out), "objects": list(data["samples"])}))


if __name__ == "__main__":
    main()
