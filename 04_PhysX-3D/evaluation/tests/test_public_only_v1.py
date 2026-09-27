import math
import unittest

import numpy as np
import trimesh

from public_only_v1 import (PublicOnlyError, aggregate_status, articulation_classification,
                            canonical_bbox, geometry_result, group_is_meaningful,
                            occurrence_rows)


def tetra(offset=(0.0, 0.0, 0.0)):
    vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float) + np.array(offset)
    return trimesh.Trimesh(vertices=vertices, faces=np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]), process=False)


class PublicOnlyV1Tests(unittest.TestCase):
    def test_identical_mesh_has_zero_cd_and_one_fscore(self):
        value = geometry_result(tetra(), tetra(), count=512, seed=7)
        self.assertEqual(value["cd_l1_sum_raw"], 0.0)
        self.assertEqual(value["cd_l2_sum_raw"], 0.0)
        self.assertEqual(value["fscore_raw"], 1.0)

    def test_translation_changes_raw_not_independent_bbox_canonical(self):
        raw = geometry_result(tetra(), tetra((3, -2, 5)), count=512, seed=7)
        canonical = geometry_result(canonical_bbox(tetra()), canonical_bbox(tetra((3, -2, 5))), count=512, seed=7)
        self.assertGreater(raw["cd_l1_sum_raw"], 0.05)
        self.assertEqual(canonical["cd_l1_sum_raw"], 0.0)
        self.assertEqual(canonical["fscore_raw"], 1.0)

    def test_empty_and_nan_mesh_fail(self):
        with self.assertRaises(PublicOnlyError):
            geometry_result(trimesh.Trimesh(vertices=np.empty((0, 3)), faces=np.empty((0, 3), dtype=int)), tetra(), count=8, seed=1)
        bad = tetra(); bad.vertices[0, 0] = math.nan
        with self.assertRaises(PublicOnlyError):
            geometry_result(bad, tetra(), count=8, seed=1)

    def test_duplicate_rows_are_preserved(self):
        rows = occurrence_rows(["1", "2", "1"], [1000, 1001, 1002])
        self.assertEqual([r["object_id"] for r in rows], ["1", "2", "1"])
        self.assertEqual([r["occurrence"] for r in rows], [1, 1, 2])

    def test_articulation_rules(self):
        self.assertTrue(articulation_classification(gt_num_group=1, predicted_num_group=2)["fixed_false_positive"])
        self.assertTrue(articulation_classification(gt_num_group=2, predicted_num_group=1)["articulated_false_negative"])
        self.assertTrue(articulation_classification(gt_num_group=4, predicted_num_group=2)["multi_joint_underprediction"])
        meaning = group_is_meaningful({"homogeneous_face_count": 100, "majority_area_fraction": .001, "components": {"largest_fraction": .01}})
        self.assertTrue(meaning["meaningful"])

    def test_status_denominators_do_not_mix(self):
        records = [{"metric": "x", "status": state, "item_key": f"k-{state}"} for state in ("success", "failed", "blocked")]
        result = aggregate_status(records, "x")
        self.assertEqual((result["declared"], result["success"], result["failed"], result["blocked"]), (3, 1, 1, 1))
        self.assertEqual(result["success_item_keys"], ["k-success"])
