"""Failure, provenance, and resume checks using only generated tiny fixtures."""
import copy
import fcntl
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import datetime
import unittest
from unittest.mock import patch

from physx_eval.common import ContractError, checked_ref, file_hash, read_json, write_new_json
from physx_eval.manifest import build_manifest, make_rows, validate_manifest
from physx_eval.mapping import validate_binding, validate_settings
from physx_eval.runner import run_session

PROJECT = Path(os.environ.get("PHYSX_ROOT", "/home/minsujo/Desktop/SH/PHYSx"))


def config(metric="scale_l2"):
    settings = {"authority": "proposal", "unit": "cm", "normalization": {"kind": "identity"},
                "representation": "scalar", "alignment": "already_aligned",
                "context": {"coordinate_frame": "synthetic_xyz", "normalization_id": "synthetic_identity"}}
    if metric.endswith("psnr"):
        settings.update(unit="synthetic_map", max_value=1.0, mask_policy="all_values",
                        zero_mse_policy="positive_infinity", view_reduction="mean_psnr")
        ctx = settings["context"]
        ctx.update(camera_set_id="fixture_set", camera_sampling="synthetic_fixture",
                   view_ids=["v0"], image_shape=[1, 2], color_space="synthetic_linear",
                   background="synthetic_zero", mask_policy="all_values",
                   camera_parameters={"extrinsic": [[int(i == j) for j in range(4)] for i in range(4)],
                                      "intrinsic": [[int(i == j) for j in range(3)] for i in range(3)],
                                      "resolution": [2, 1], "near": 0.1, "far": 10,
                                      "convention": "synthetic_camera_to_world"})
        if metric != "appearance_psnr":
            ctx["part_correspondence"] = "explicit_file_map"
        if metric == "description_psnr":
            ctx.update(question_type="basic", question_text="synthetic part",
                       question_target_part="0", gt_map_definition="synthetic_binary",
                       text_encoder_revision="synthetic_no_model")
    return {"schema_version": 1, "claim": "proposal_cpu_check", "execution_scope": "synthetic_fixture",
            "failure_mode": "stop", "metrics": {metric: settings},
            "aggregation": {"mode": "disabled", "duplicate_policy": None,
                            "failure_policy": None, "denominator": None}}


class FixtureCase(unittest.TestCase):
    def setUp(self):
        # Kept inside the logged sandbox run; no data/model files are involved.
        self.root = Path(tempfile.mkdtemp(prefix="fixture-", dir=os.environ["PHYSX_TEST_TMP"]))
        self.cfg = config()
        self.manifest = {"schema_version": 1, "kind": "synthetic_fixture", "paper_equivalent": False,
                         "duplicate_aggregation_policy": None, "items": make_rows(["001", "001", "002"], 0)}
        self.prepare()

    def ref(self, path):
        return {"path": str(path.relative_to(self.root)), "sha256": file_hash(path)}

    def prepare(self, metric="scale_l2"):
        self.cfg = config(metric)
        settings = self.cfg["metrics"][metric]
        for item in self.manifest["items"]:
            folder = self.root / item["item_key"] / metric
            folder.mkdir(parents=True, exist_ok=True)
            image = folder / "input.txt"
            image.write_text("synthetic input identity " + item["item_key"])
            input_ref = dict(self.ref(image), object_id=item["object_id"], view_id="conditioning_v0")
            binding = {"input": input_ref}
            for role in ["prediction", "ground_truth"]:
                values = [5] if role == "prediction" else [2]
                payload = {"values": values, "unit": settings["unit"]}
                if metric.endswith("psnr"):
                    payload.update(values=[[0, 1]] if role == "prediction" else [[0, 0]], view_id="v0")
                artifact = {"schema_version": 1, "role": role, "item_key": item["item_key"],
                            "object_id": item["object_id"], "source_index": item["source_index"],
                            "input_sha256": input_ref["sha256"], "input_view_id": input_ref["view_id"],
                            "context": settings["context"], "payload": payload}
                path = folder / (role + ".json")
                path.write_text(json.dumps(artifact))
                binding[role] = self.ref(path)
            if metric in {"density_psnr", "affordance_psnr", "description_psnr"}:
                mesh = folder / "0.obj"; mesh.write_text("# tiny fixture, not a parsed real mesh\n")
                annotation = folder / "annotation.json"
                annotation.write_text(json.dumps({"object_id": item["object_id"], "parts": [{"label": "0"}]}))
                binding["parts"] = [{"label": "0", "parts_index": 0, "mesh_filename": "0.obj", "mesh": self.ref(mesh)}]
                binding["annotation"] = self.ref(annotation)
            item["bindings"] = {metric: binding}

    def rewrite_artifact(self, item, metric, role, mutate):
        ref = item["bindings"][metric][role]
        path = self.root / ref["path"]
        value = read_json(path); mutate(value)
        path.write_text(json.dumps(value))
        ref["sha256"] = file_hash(path)

    def run_fixture(self, retry=False):
        return run_session(self.root, self.manifest, self.cfg, "session", retry_failed=retry)


class ManifestTests(FixtureCase):
    def test_checked_in_configs_have_no_silent_evaluation_defaults(self):
        directory = Path(__file__).resolve().parents[1] / "configs"
        self.assertEqual(read_json(directory / "synthetic-scale.json"), self.cfg)
        unresolved = read_json(directory / "unresolved.json")
        from physx_eval.mapping import validate_settings
        for name, settings in unresolved["metrics"].items():
            with self.subTest(metric=name), self.assertRaises(ContractError):
                validate_settings(name, settings)

    def test_duplicate_ids_are_distinct_rows_without_weights(self):
        result = validate_manifest(self.root, self.manifest)
        self.assertEqual((result["rows"], result["unique_ids"]), (3, 2))
        self.assertEqual([x["occurrence"] for x in self.manifest["items"]], [1, 2, 1])
        self.assertEqual(len({x["item_key"] for x in self.manifest["items"]}), 3)
        self.assertIsNone(result["duplicate_aggregation_policy"])

    def test_reordered_duplicate_rows_wrong_indices_and_dedup_are_rejected(self):
        for mutation in (lambda items: items.reverse(), lambda items: items.pop(0),
                         lambda items: items[1].update(occurrence=1),
                         lambda items: items[0].update(source_index=True)):
            manifest = copy.deepcopy(self.manifest); mutation(manifest["items"])
            with self.assertRaises((ContractError, ValueError)):
                validate_manifest(self.root, manifest)

    def test_official_manifest_matches_existing_original_test_order(self):
        # Read existing local metadata only. No new archive or data is downloaded.
        prefix = "repro-records/04_PhysX-3D/평가규약/2026-09-21_초안/"
        result = build_manifest(PROJECT, prefix + "test-input-gt-correspondence.csv",
                                "sources/physx-4f54e750a309/val_test_list.npy")
        self.assertEqual(len(result["items"]), 1000)
        self.assertEqual(len({x["object_id"] for x in result["items"]}), 972)
        self.assertEqual([x["source_index"] for x in result["items"]], list(range(1000, 2000)))
        self.assertTrue(all(x["bindings"] == {} for x in result["items"]))
        write_new_json(self.root / "official-manifest.json", result)
        result["items"][1]["object_id"] = "wrong"
        with self.assertRaises(ContractError):
            validate_manifest(PROJECT, result)


class MappingTests(FixtureCase):
    def test_json_duplicate_keys_and_nonfinite_exponents_are_rejected(self):
        path = self.root / "invalid.json"
        for content in ['{"x":1,"x":2}', '{"x":NaN}', '{"x":1e309}']:
            path.write_text(content)
            with self.subTest(content=content), self.assertRaises(ContractError):
                read_json(path)

    def test_valid_pair_and_duplicate_identity(self):
        item = self.manifest["items"][0]
        pred, gt = validate_binding(self.root, item, "scale_l2", self.cfg["metrics"]["scale_l2"])
        self.assertEqual(pred["values"], [5]); self.assertEqual(gt["values"], [2])
        item["bindings"]["scale_l2"]["ground_truth"] = self.manifest["items"][1]["bindings"]["scale_l2"]["ground_truth"]
        with self.assertRaisesRegex(ContractError, "identity"):
            validate_binding(self.root, item, "scale_l2", self.cfg["metrics"]["scale_l2"])

    def test_hash_missing_input_and_path_escape(self):
        binding = self.manifest["items"][0]["bindings"]["scale_l2"]
        path = self.root / binding["input"]["path"]; path.write_text("changed")
        with self.assertRaisesRegex(ContractError, "hash mismatch"):
            checked_ref(self.root, binding["input"])
        path.unlink()
        with self.assertRaisesRegex(ContractError, "missing"):
            checked_ref(self.root, binding["input"])
        with self.assertRaisesRegex(ContractError, "escapes"):
            checked_ref(self.root, {"path": "/etc/passwd", "sha256": "0" * 64})

    def test_symlink_escape_is_not_allowed(self):
        path = self.root / "outside"; path.symlink_to("/etc/passwd")
        with self.assertRaisesRegex(ContractError, "escapes"):
            checked_ref(self.root, {"path": "outside", "sha256": "0" * 64})

    def test_camera_question_unit_and_part_correspondence(self):
        self.prepare("description_psnr")
        item = self.manifest["items"][0]; settings = self.cfg["metrics"]["description_psnr"]
        validate_binding(self.root, item, "description_psnr", settings)
        for field in ["camera_set_id", "camera_parameters", "question_text", "question_target_part", "gt_map_definition"]:
            broken = copy.deepcopy(settings); del broken["context"][field]
            with self.subTest(field=field), self.assertRaises(ContractError):
                validate_binding(self.root, item, "description_psnr", broken)
        self.rewrite_artifact(item, "description_psnr", "ground_truth", lambda a: a["payload"].update(unit="other"))
        with self.assertRaisesRegex(ContractError, "unit"):
            validate_binding(self.root, item, "description_psnr", settings)

    def test_part_label_index_is_not_assumed_from_filename(self):
        self.prepare("density_psnr"); item = self.manifest["items"][0]
        item["bindings"]["density_psnr"]["parts"][0]["label"] = "not_zero"
        with self.assertRaisesRegex(ContractError, "label/index"):
            validate_binding(self.root, item, "density_psnr", self.cfg["metrics"]["density_psnr"])

    def test_view_input_question_context_and_shape_mismatch(self):
        self.prepare("appearance_psnr"); item = self.manifest["items"][0]
        original = copy.deepcopy(item["bindings"])
        for mutate in [lambda a: a.update(input_view_id="wrong"),
                       lambda a: a.update(input_sha256="0" * 64),
                       lambda a: a["context"].update(camera_set_id="wrong"),
                       lambda a: a["payload"].update(values=[0, 1]),
                       lambda a: a["payload"].update(view_id="wrong")]:
            # Restore the actual artifact as well as the descriptor between cases.
            self.prepare("appearance_psnr"); item = self.manifest["items"][0]
            self.rewrite_artifact(item, "appearance_psnr", "ground_truth", mutate)
            with self.assertRaises(ContractError):
                validate_binding(self.root, item, "appearance_psnr", self.cfg["metrics"]["appearance_psnr"])


class ResumeTests(FixtureCase):
    def test_success_resume_preserves_completed_attempts_and_no_final_mean(self):
        first = self.run_fixture()
        self.assertEqual(first["counts"]["success"], 3)
        before = {str(p): p.read_bytes() for p in (self.root / "session/items").rglob("*") if p.is_file()}
        second = self.run_fixture()
        self.assertEqual(second["counts"]["reused_success"], 3)
        after = {str(p): p.read_bytes() for p in (self.root / "session/items").rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertIsNone(second["aggregation"]["final_score"])
        self.assertEqual(second["aggregation"]["status"], "blocked")

    def test_failure_stops_then_explicit_retry_preserves_failed_attempt(self):
        with patch("physx_eval.runner.evaluate", side_effect=RuntimeError("synthetic transient failure")):
            failed = self.run_fixture()
        self.assertEqual(failed["counts"]["failed"], 1)
        self.assertEqual(failed["counts"]["not_attempted"], 2)
        old = sorted((self.root / "session/items").rglob("result.json"))[0]
        old_bytes = old.read_bytes()
        refused = self.run_fixture()
        self.assertEqual(refused["counts"]["retry_required"], 1)
        self.assertEqual(self.run_fixture(retry=True)["counts"]["success"], 3)
        self.assertEqual(old.read_bytes(), old_bytes)

    def test_missing_setting_records_blocked_without_default(self):
        del self.cfg["metrics"]["scale_l2"]["unit"]
        result = self.run_fixture()
        self.assertEqual(result["counts"]["blocked"], 1)
        self.assertEqual(result["counts"]["not_attempted"], 2)

    def test_scale_representation_is_required_by_preflight(self):
        settings = copy.deepcopy(self.cfg["metrics"]["scale_l2"])
        del settings["representation"]
        with self.assertRaisesRegex(ContractError, "representation"):
            validate_settings("scale_l2", settings)

    def test_changed_config_manifest_code_block_reuse(self):
        self.run_fixture()
        old = copy.deepcopy(self.cfg)
        self.cfg["metrics"]["scale_l2"]["normalization"] = {"kind": "fixed_affine", "scale": 2, "offset": 0}
        with self.assertRaisesRegex(ContractError, "contract changed"):
            self.run_fixture()
        self.cfg = old
        with patch("physx_eval.runner.code_hash", return_value="changed"):
            with self.assertRaisesRegex(ContractError, "contract changed"):
                self.run_fixture()
        self.manifest["items"][0]["bindings"]["scale_l2"]["input"]["view_id"] = "changed"
        with self.assertRaisesRegex(ContractError, "contract changed"):
            self.run_fixture()

    def test_changed_artifact_is_revalidated_before_skip(self):
        self.run_fixture()
        ref = self.manifest["items"][0]["bindings"]["scale_l2"]["input"]
        (self.root / ref["path"]).write_text("corrupted input")
        result = self.run_fixture()
        self.assertEqual(result["counts"]["blocked"], 1)
        self.assertEqual(result["counts"]["reused_success"], 0)

    def test_interrupted_or_corrupt_result_requires_retry_and_keeps_evidence(self):
        self.run_fixture()
        result_path = sorted((self.root / "session/items").rglob("result.json"))[0]
        result_path.write_text("partial-json")
        self.assertEqual(self.run_fixture()["counts"]["retry_required"], 1)
        self.assertEqual(self.run_fixture(retry=True)["counts"]["success"], 1)
        self.assertEqual(result_path.read_text(), "partial-json")

    def test_session_lock_prevents_duplicate_work(self):
        session = self.root / "session"; session.mkdir()
        with (session / ".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ContractError, "already running"):
                self.run_fixture()

    def test_other_item_success_record_is_not_reused(self):
        self.run_fixture()
        results = sorted((self.root / "session/items").rglob("result.json"))
        for name in ["result.json", "completion.json"]:
            (results[0].parent / name).write_bytes((results[1].parent / name).read_bytes())
        retry = self.run_fixture()
        self.assertEqual(retry["counts"]["retry_required"], 1)
        self.assertEqual(retry["counts"]["reused_success"], 0)

    def test_valid_json_wrong_record_types_are_recoverable_only_by_explicit_retry(self):
        self.run_fixture()
        for filename, content in [("result.json", "[]"), ("completion.json", "null")]:
            attempts = sorted((self.root / "session/items/test-000000/scale_l2").glob("attempt-*"))
            bad = attempts[-1] / filename
            bad.write_text(content)
            self.assertEqual(self.run_fixture()["counts"]["retry_required"], 1)
            self.assertEqual(self.run_fixture(retry=True)["counts"]["success"], 1)
            self.assertEqual(bad.read_text(), content)

    def test_invalid_gt_json_type_is_logged_as_blocked(self):
        item = self.manifest["items"][0]
        ref = item["bindings"]["scale_l2"]["ground_truth"]
        path = self.root / ref["path"]; path.write_text("[]")
        ref["sha256"] = file_hash(path)
        result = self.run_fixture()
        self.assertEqual(result["counts"]["blocked"], 1)
        self.assertEqual(result["counts"]["not_attempted"], 2)

    def test_missing_or_changed_snapshot_blocks_resume(self):
        self.run_fixture()
        snapshot = self.root / "session/config.json"
        snapshot.write_text("{}")
        with self.assertRaisesRegex(ContractError, "snapshot"):
            self.run_fixture()

    def test_aggregation_real_execution_and_paper_claims_are_blocked(self):
        for key, value in [("claim", "paper_equivalent"), ("execution_scope", "official_test"),
                           ("aggregation", {"mode": "mean", "denominator": 972})]:
            original = copy.deepcopy(self.cfg); self.cfg[key] = value
            with self.subTest(key=key), self.assertRaises(ContractError):
                self.run_fixture()
            self.cfg = original


class CLITests(FixtureCase):
    def command(self, name, *args):
        code = Path(__file__).resolve().parents[1] / "cli.py"
        folder = self.root / ("cli-" + name); folder.mkdir()
        argv = [sys.executable, "-I", "-B", "-S", str(code), "--root", str(self.root), *args]
        start = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write_new_json(folder / "command.json", {"argv": argv, "started_at": start})
        with (folder / "stdout.log").open("x") as out, (folder / "stderr.log").open("x") as err:
            result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
        write_new_json(folder / "result.json", {"exit_code": result.returncode, "started_at": start,
                       "ended_at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
        return result.returncode

    def test_cli_run_resume_and_unresolved_validation(self):
        write_new_json(self.root / "manifest.json", self.manifest)
        write_new_json(self.root / "config.json", self.cfg)
        args = ["synthetic-run", "--manifest", "manifest.json", "--config", "config.json", "--session", "session"]
        self.assertEqual(self.command("run", *args), 0)
        self.assertEqual(self.command("resume", *args), 0)
        returned = read_json(self.root / "cli-resume/stdout.log")
        self.assertEqual(returned["counts"]["reused_success"], 3)
        unresolved = copy.deepcopy(self.cfg); unresolved["metrics"]["scale_l2"]["unit"] = None
        write_new_json(self.root / "unresolved.json", unresolved)
        self.assertEqual(self.command("blocked", "validate", "--manifest", "manifest.json", "--config",
                                     "unresolved.json", "--output", "validation.json"), 2)
        self.assertTrue(all(x["status"] == "blocked" for x in read_json(self.root / "validation.json")["bindings"]))

    def test_cli_does_not_overwrite_existing_validation(self):
        write_new_json(self.root / "manifest.json", self.manifest)
        write_new_json(self.root / "config.json", self.cfg)
        write_new_json(self.root / "validation.json", {"preserve": True})
        self.assertEqual(self.command("exclusive", "validate", "--manifest", "manifest.json", "--config",
                                     "config.json", "--output", "validation.json"), 2)
        self.assertEqual(read_json(self.root / "validation.json"), {"preserve": True})


if __name__ == "__main__":
    unittest.main()
