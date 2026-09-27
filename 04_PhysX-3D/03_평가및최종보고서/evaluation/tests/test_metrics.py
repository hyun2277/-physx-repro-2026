"""Analytic CPU fixtures. These are proposal checks, not PhysX benchmark scores."""

import copy
import json
import math
import unittest

from physx_eval.metrics import MetricError, evaluate, mean_appearance_psnr_30


def common(unit="synthetic_length"):
    return {"authority": "proposal", "normalization": {"kind": "identity"}, "unit": unit}


def psnr_settings():
    return dict(
        common("synthetic_map"), max_value=1.0, mask_policy="all_values",
        zero_mse_policy="positive_infinity", view_reduction="mean_psnr",
    )


def geometry_settings():
    return dict(
        common(), coordinate_frame="synthetic_xyz", point_sampling="explicit_fixture_points",
        distance="euclidean",
    )


def cd_settings():
    return dict(geometry_settings(), direction_reduction="sum")


def fscore_settings():
    return dict(
        geometry_settings(), threshold=0.05, threshold_interpretation="euclidean_radius",
        comparison="le", zero_precision_recall="zero",
    )


def image(values, view_id="synthetic_view"):
    return {"values": values, "unit": "synthetic_map", "view_id": view_id}


def points(xs):
    return {"points": [[x, 0.0, 0.0] for x in xs], "unit": "synthetic_length"}


class PSNRTests(unittest.TestCase):
    def test_all_psnr_names_use_hand_computed_mse(self):
        # Errors 0 and 1 => MSE=1/2; PSNR=10*log10(2).
        for metric in ("appearance_psnr", "density_psnr", "affordance_psnr", "description_psnr"):
            with self.subTest(metric=metric):
                result = evaluate(metric, image([[0.0, 1.0]]), image([[0.0, 0.0]]), psnr_settings())
                self.assertAlmostEqual(result["mse"], 0.5)
                self.assertAlmostEqual(result["raw"], 10 * math.log10(2))
                self.assertEqual(result["scope"], "single_view")
                self.assertFalse(result["paper_equivalent"])
                self.assertEqual(result["authority"], "proposal")

    def test_identical_constant_maps_have_explicit_infinity(self):
        result = evaluate("density_psnr", image([[3, 3]]), image([[3, 3]]), psnr_settings())
        self.assertEqual(result["raw"], "+inf")
        self.assertEqual(result["mse"], 0)
        json.dumps(result, allow_nan=False)
        settings = dict(psnr_settings(), zero_mse_policy="error")
        with self.assertRaisesRegex(MetricError, "zero MSE"):
            evaluate("density_psnr", image([3]), image([3]), settings)

    def test_distinct_constant_maps_do_not_trigger_minmax_normalization(self):
        settings = dict(psnr_settings(), max_value=2)
        result = evaluate("affordance_psnr", image([1, 1]), image([0, 0]), settings)
        self.assertAlmostEqual(result["raw"], 20 * math.log10(2))
        self.assertEqual(result["mse"], 1)

    def test_same_fixed_affine_is_applied_to_both_maps(self):
        settings = psnr_settings()
        settings["normalization"] = {"kind": "fixed_affine", "scale": 0.5, "offset": 3}
        result = evaluate("description_psnr", image([1]), image([0]), settings)
        self.assertAlmostEqual(result["mse"], 0.25)
        self.assertAlmostEqual(result["raw"], 20 * math.log10(2))

    def test_view_and_shape_must_match(self):
        for pred, gt in ((image([0], "a"), image([0], "b")), (image([[0, 0]]), image([0, 0]))):
            with self.subTest(pred=pred, gt=gt), self.assertRaises(MetricError):
                evaluate("appearance_psnr", pred, gt, psnr_settings())
        pred = image([0])
        del pred["view_id"]
        with self.assertRaises(MetricError):
            evaluate("appearance_psnr", pred, image([0]), psnr_settings())

    def test_invalid_values_do_not_become_scores(self):
        for values in ([], [[]], [[1], [1, 2]], [float("nan")], [float("inf")], [True], ["1"]):
            with self.subTest(values=values), self.assertRaises(MetricError):
                evaluate("appearance_psnr", image(values), image(values), psnr_settings())

    def test_numerical_overflow_and_underflow_are_reported(self):
        for value in (1e308, 1e-200):
            with self.subTest(value=value), self.assertRaises(MetricError):
                evaluate("appearance_psnr", image([value]), image([0]), psnr_settings())


class ThirtyViewAppearanceTests(unittest.TestCase):
    def records(self):
        view_ids = [f"synthetic_view_{index:02d}" for index in range(30)]
        records = [
            {
                "metric": "appearance_psnr", "scope": "single_view", "view_id": view_id,
                "raw": 20.0 if index < 15 else 0.0, "unit": "dB",
                "authority": "proposal", "paper_equivalent": False,
            }
            for index, view_id in enumerate(view_ids)
        ]
        return records, view_ids

    def test_mean_of_psnr_is_not_psnr_of_pooled_mse(self):
        # MAX=1: 20 dB implies MSE=.01, and 0 dB implies MSE=1.
        # The mean of fifteen of each PSNR is 10 dB; pooled MSE gives ~2.967 dB.
        records, view_ids = self.records()
        result = mean_appearance_psnr_30(records, view_ids, infinite_policy="error")
        self.assertAlmostEqual(result["raw"], 10)
        pooled_mse_psnr = -10 * math.log10((0.01 + 1) / 2)
        self.assertAlmostEqual(pooled_mse_psnr, 2.967086218813386)
        self.assertNotAlmostEqual(result["raw"], pooled_mse_psnr)
        self.assertEqual(result["view_count"], 30)
        self.assertEqual(result["view_ids"], view_ids)
        self.assertEqual(result["authority"], "proposal")
        self.assertFalse(result["paper_equivalent"])
        json.dumps(result, allow_nan=False)

    def test_requires_all_30_distinct_expected_views(self):
        records, view_ids = self.records()
        for bad_records, bad_ids in (
            (records[:-1], view_ids), (records, view_ids[:-1]),
            (records + records[:1], view_ids), (records, view_ids[:-1] + view_ids[:1]),
            (records, [""] + view_ids[1:]), (records, [None] + view_ids[1:]),
            (records, ["UNRESOLVED"] + view_ids[1:]),
        ):
            with self.subTest(ids=bad_ids), self.assertRaises(MetricError):
                mean_appearance_psnr_30(bad_records, bad_ids, infinite_policy="error")

    def test_duplicate_mismatched_and_reordered_results_are_rejected(self):
        records, view_ids = self.records()
        for bad_records in (
            records[:-1] + records[:1], list(reversed(records)),
            [dict(records[0], view_id="different_view")] + records[1:],
        ):
            with self.subTest(first=bad_records[0]), self.assertRaises(MetricError):
                mean_appearance_psnr_30(bad_records, view_ids, infinite_policy="error")

    def test_record_type_metric_scope_authority_and_finite_values_are_checked(self):
        records, view_ids = self.records()
        invalid_records = [
            dict(records[0], metric="density_psnr"), dict(records[0], scope="mean_of_30_views"),
            dict(records[0], authority="paper_equivalent"), dict(records[0], paper_equivalent=True),
            dict(records[0], paper_equivalent=0), dict(records[0], unit="unknown"),
            dict(records[0], raw=float("nan")), dict(records[0], raw=float("inf")),
            dict(records[0], raw=float("-inf")), dict(records[0], raw=True),
            dict(records[0], raw=None), dict(records[0], raw="20"), None,
        ]
        for bad_record in invalid_records:
            with self.subTest(record=bad_record), self.assertRaises(MetricError):
                mean_appearance_psnr_30([bad_record] + records[1:], view_ids, infinite_policy="error")

    def test_infinity_policy_is_explicit_and_does_not_clip(self):
        records, view_ids = self.records()
        records[0]["raw"] = "+inf"
        with self.assertRaisesRegex(MetricError, "infinite view PSNR"):
            mean_appearance_psnr_30(records, view_ids, infinite_policy="error")
        result = mean_appearance_psnr_30(records, view_ids, infinite_policy="positive_infinity")
        self.assertEqual(result["raw"], "+inf")
        json.dumps(result, allow_nan=False)
        for policy in (None, "unknown", "clip", "", []):
            with self.subTest(policy=policy), self.assertRaises(MetricError):
                mean_appearance_psnr_30(records, view_ids, infinite_policy=policy)
        with self.assertRaises(TypeError):
            mean_appearance_psnr_30(records, view_ids)


class GeometryTests(unittest.TestCase):
    def test_cd_directional_terms_sum_mean_and_squared_definitions(self):
        # P={0,2}, G={0}; unsquared directional means=(1,0), squared=(2,0).
        for distance, reduction, expected in (
            ("euclidean", "sum", 1), ("euclidean", "mean", 0.5),
            ("squared_euclidean", "sum", 2), ("squared_euclidean", "mean", 1),
        ):
            with self.subTest(distance=distance, reduction=reduction):
                settings = dict(cd_settings(), distance=distance, direction_reduction=reduction)
                result = evaluate("cd", points([0, 2]), points([0]), settings)
                self.assertEqual(result["raw"], expected)
                self.assertEqual(result["display_value"], expected * 1000)
                self.assertEqual(result["gt_to_pred_mean"], 0)
                self.assertFalse(result["paper_equivalent"])

    def test_fscore_uses_separate_directional_hit_denominators(self):
        # P={0,.01,1}, G={0,2}; P_hits=2/3, R_hits=1/2 => F=4/7.
        result = evaluate("fscore", points([0, 0.01, 1]), points([0, 2]), fscore_settings())
        self.assertEqual(result["pred_hits"], 2)
        self.assertEqual(result["gt_hits"], 1)
        self.assertAlmostEqual(result["precision"], 2 / 3)
        self.assertEqual(result["recall"], 0.5)
        self.assertAlmostEqual(result["raw"], 4 / 7)
        self.assertAlmostEqual(result["display_value"], 400 / 7)

    def test_equal_point_counts_can_still_have_different_hit_counts(self):
        # P_hits=2/3 and R_hits=1/3, even though both clouds contain three points.
        result = evaluate("fscore", points([0, 0.01, 1]), points([0, 2, 3]), fscore_settings())
        self.assertAlmostEqual(result["precision"], 2 / 3)
        self.assertAlmostEqual(result["recall"], 1 / 3)
        self.assertAlmostEqual(result["raw"], 4 / 9)

    def test_squared_distance_maps_radius_to_squared_threshold(self):
        for distance in ("euclidean", "squared_euclidean"):
            settings = dict(fscore_settings(), distance=distance)
            result = evaluate("fscore", points([0.05]), points([0]), settings)
            self.assertEqual(result["raw"], 1)
            self.assertAlmostEqual(result["effective_distance_threshold"], 0.05 if distance == "euclidean" else 0.0025)
            outside = evaluate("fscore", points([0.051]), points([0]), settings)
            self.assertEqual(outside["raw"], 0)
            settings["comparison"] = "lt"
            boundary = evaluate("fscore", points([0.05]), points([0]), settings)
            self.assertEqual(boundary["raw"], 0)

    def test_euclidean_radius_cannot_be_replaced_by_squared_value(self):
        for settings in (
            dict(fscore_settings(), threshold=0.0025),
            dict(fscore_settings(), threshold_interpretation="squared_radius"),
        ):
            with self.assertRaises(MetricError):
                evaluate("fscore", points([0]), points([0]), settings)

    def test_zero_hit_policy_is_required_and_respected(self):
        result = evaluate("fscore", points([1]), points([0]), fscore_settings())
        self.assertEqual(result["raw"], 0)
        settings = dict(fscore_settings(), zero_precision_recall="error")
        with self.assertRaisesRegex(MetricError, "zero precision"):
            evaluate("fscore", points([1]), points([0]), settings)

    def test_empty_wrong_shape_and_nonfinite_points_rejected(self):
        for bad in ([], [[1, 2]], [[0, 0, 0], [1]], [[float("inf"), 0, 0]]):
            pred = {"points": bad, "unit": "synthetic_length"}
            with self.subTest(bad=bad), self.assertRaises(MetricError):
                evaluate("cd", pred, points([0]), cd_settings())

    def test_display_conversion_is_derived_once_from_raw(self):
        first = evaluate("cd", points([0.001]), points([0]), cd_settings())
        second = evaluate("cd", points([0.001]), points([0]), cd_settings())
        self.assertEqual(first, second)
        self.assertAlmostEqual(first["raw"], 0.002)
        self.assertAlmostEqual(first["display_value"], 2)
        result = evaluate("fscore", points([0]), points([0]), fscore_settings())
        self.assertEqual(result["raw"], 1)
        self.assertEqual(result["display_value"], 100)


class ScaleAndSettingsTests(unittest.TestCase):
    def test_scale_scalar_and_vector_are_euclidean(self):
        scalar = dict(common("cm"), representation="scalar")
        result = evaluate("scale_l2", {"values": [5], "unit": "cm"}, {"values": [2], "unit": "cm"}, scalar)
        self.assertEqual(result["raw"], 3)
        vector = dict(common("cm"), representation="vector")
        result = evaluate("scale_l2", {"values": [3, 4], "unit": "cm"}, {"values": [0, 0], "unit": "cm"}, vector)
        self.assertEqual(result["raw"], 5)

    def test_scale_units_shape_and_representation_are_not_inferred(self):
        settings = dict(common("cm"), representation="scalar")
        for pred in ({"values": [1], "unit": "m"}, {"values": [1, 2], "unit": "cm"}, {"values": [], "unit": "cm"}):
            with self.subTest(pred=pred), self.assertRaises(MetricError):
                evaluate("scale_l2", pred, {"values": [0], "unit": "cm"}, settings)

    def test_every_required_setting_is_mandatory(self):
        cases = (
            ("appearance_psnr", image([1]), image([0]), psnr_settings()),
            ("cd", points([0]), points([0]), cd_settings()),
            ("fscore", points([0]), points([0]), fscore_settings()),
            ("scale_l2", {"values": [1], "unit": "cm"}, {"values": [0], "unit": "cm"}, dict(common("cm"), representation="scalar")),
        )
        for metric, pred, gt, full in cases:
            for key in full:
                with self.subTest(metric=metric, missing=key):
                    settings = copy.deepcopy(full)
                    del settings[key]
                    with self.assertRaises(MetricError):
                        evaluate(metric, pred, gt, settings)

    def test_unresolved_settings_and_paper_equivalence_authority_rejected(self):
        for value in (None, "UNRESOLVED", "unknown", "미확정", "", "paper_equivalent"):
            settings = dict(psnr_settings(), authority=value)
            with self.subTest(value=value), self.assertRaises(MetricError):
                evaluate("appearance_psnr", image([1]), image([0]), settings)
        settings = dict(psnr_settings(), camera={"seed": None})
        with self.assertRaises(MetricError):
            evaluate("appearance_psnr", image([1]), image([0]), settings)

    def test_normalization_is_explicit_and_disallows_per_item_minmax(self):
        for normalization in (
            {"kind": "minmax"}, {"kind": "fixed_affine", "scale": 0, "offset": 0},
            {"kind": "fixed_affine", "scale": 1}, {"kind": "identity", "scale": 1},
            {"kind": "fixed_affine", "scale": 1, "offset": None},
        ):
            with self.subTest(normalization=normalization), self.assertRaises(MetricError):
                evaluate("appearance_psnr", image([1]), image([0]), dict(psnr_settings(), normalization=normalization))

    def test_invalid_numeric_settings_rejected(self):
        for value in (0, -1, True, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(MetricError):
                evaluate("appearance_psnr", image([1]), image([0]), dict(psnr_settings(), max_value=value))

    def test_joint_set_metrics_are_explicitly_unimplemented(self):
        for metric in ("cov", "mmd"):
            with self.subTest(metric=metric), self.assertRaisesRegex(MetricError, "ID/aggregation unresolved"):
                evaluate(metric, {}, {}, {})

    def test_code_verified_label_still_never_claims_paper_equivalence(self):
        result = evaluate("cd", points([0]), points([0]), dict(cd_settings(), authority="code_verified"))
        self.assertFalse(result["paper_equivalent"])
        json.dumps(result, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
