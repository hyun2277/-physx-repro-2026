#!/usr/bin/env python3
"""Publish the v1 result update from existing extension-run artifacts only.

No model, Blender, or GPU operation is performed here.  This wraps the v1
CPU evaluator with five newly verified outputs and records the sixth selected
sample as failed rather than silently omitting it.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_public_only_v1 as base

OUT = HERE / "2026-09-27_public-only-v1-extension-8"
ROOT = Path("/home/minsujo/Desktop/SH/PHYSx")
BATCH = ROOT / "logs/public-only-v1-extension/20260927T091659Z-9a8c49d58c7f"

RUNS = {
    "21356": ("20260927T091739Z-a3a281fd06a9", "20260927T092106Z-ffa272c5ba06"),
    "27703": ("20260927T092210Z-6cfe9750da0b", "20260927T092515Z-2f14d516dff6"),
    "30719": ("20260927T092619Z-0f8f04fa744c", "20260927T092901Z-d538b15f6c99"),
    "21314": ("20260927T093004Z-979aaffdfc05", "20260927T093243Z-8f56ad081b93"),
    "32980": ("20260927T093342Z-974dd9c24a99", "20260927T093615Z-1863e3e10709"),
}


def spec(object_id, sampling_id, decoder_id):
    sampling = ROOT / f"staging/articulated-sampling-{object_id}-{sampling_id}"
    decoder = ROOT / f"staging/public-only-v1-extension-decoder-{object_id}-{decoder_id}"
    return {
        "gt_json": str(sampling / f"work/physxnet/finaljson/{object_id}.json"),
        "gt_mesh": str(sampling / f"work/phy_dataset/{object_id}/model.obj"),
        "generated_mesh": str(decoder / "mesh/mesh.obj"),
        "property": str(decoder / "articulation_audit/vertex_physics_14ch.pt"),
        "audit": str(decoder / "articulation_audit/official_result.json"),
    }


def main():
    if OUT.exists():
        raise RuntimeError(f"refusing to overwrite result folder: {OUT}")
    base.OUT = OUT
    base.SAMPLES.update({object_id: spec(object_id, *run_ids) for object_id, run_ids in RUNS.items()})
    base.main()  # CPU-only geometry, scale, and articulation diagnostics.
    failed = {
        "object_id":"23787", "status":"failed", "stage":"official_texture_retrieval",
        "reason":"official retrieval output failed the object-independent finite-OBJ verifier; model_tex.obj contains non-finite data",
        "sampling_or_decoder_retried":False,
        "source_run":str(ROOT / "logs/articulated-sampling-only/23787/20260927T093713Z-5770940f5def"),
    }
    summary = {
        "protocol":"public-materials-independent-evaluation-v1", "paper_equivalent":False,
        "selected_ids":["21356","27703","30719","21314","32980","23787"],
        "generated_artifact_ids":["29354","24566","29806",*RUNS.keys()],
        "generated_artifact_count":8,
        "planned_total":9,
        "not_silently_excluded":[failed],
        "selection_batch":str(BATCH),
        "memory_note":"All five decoded extension candidates passed their per-latent measured gate; no GPU memory gate rejection or OOM occurred. 27281 remains excluded by prior observed unsafe decoder memory evidence.",
        "partnet_note":"PartNet was not used: JSON and part OBJ inputs came from the already present PhysXNet ZIP, and texture members came from the existing ShapeNet 04379243 ZIP.",
    }
    (OUT / "extension_execution_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    (OUT / "README.md").write_text(
        "# Public-only v1 extension execution\n\n"
        "This is a proposed public-materials independent evaluation condition, not a reproduction of PhysX-3D Table 2 or its official evaluation. "
        "It reuses the existing 29354/24566/29806 results and adds five generated artifacts. 23787 remains a recorded failure: its official texture-retrieval output failed the finite-OBJ verifier, so it was not retried or treated as a zero score.\n\n"
        "`results.json`, `records.csv`, and `manifest.json` contain CPU-computed geometry, scalar scale, and group-surface diagnostics for the eight artifact-complete samples. "
        "Appearance, density, affordance, description, parent/axis/range accuracy, 30-view evaluation, and paper-level aggregation remain blocked under the v1 protocol.\n",
        encoding="utf-8")
    print(json.dumps({"output":str(OUT), **summary}, ensure_ascii=False))


if __name__ == "__main__": main()
