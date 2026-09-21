"""Small, dependency-free CPU metric primitives with explicit assumptions.

These functions verify numerical formulas on already aligned numerical payloads.
They do not render, sample meshes, align coordinate systems, infer units, choose
cameras, or aggregate benchmark items. A successful return is never a claim of
paper-equivalent evaluation. Geometry nearest neighbours use O(N*M) CPU work;
this module is intended for small fixtures, not a full benchmark implementation.
"""

from __future__ import annotations

import math

from .contracts import validate_metric_contract


class MetricError(ValueError):
    """A payload, required setting, or numerical operation is not valid."""


_PSNR_METRICS = {
    "appearance_psnr", "density_psnr", "affordance_psnr", "description_psnr"
}
_UNRESOLVED = {"unknown", "unresolved", "tbd", "todo", "null", "none", "미확정", "?"}


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MetricError(f"{label}: expected a finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise MetricError(f"{label}: number cannot be represented") from exc
    if not math.isfinite(result):
        raise MetricError(f"{label}: expected a finite number")
    return result


def _finite(value, label):
    if not math.isfinite(value):
        raise MetricError(f"{label}: numerical overflow or nonfinite result")
    return value


def _resolved(value, label):
    """Reject explicit unknown placeholders, including nested configuration."""
    if value is None:
        raise MetricError(f"{label}: unresolved/null setting")
    if isinstance(value, str) and (
        not value.strip() or value.strip().casefold() in _UNRESOLVED
    ):
        raise MetricError(f"{label}: unresolved/empty setting")
    if isinstance(value, float) and not math.isfinite(value):
        raise MetricError(f"{label}: nonfinite setting")
    if isinstance(value, dict):
        for key, item in value.items():
            _resolved(item, f"{label}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _resolved(item, f"{label}[{index}]")


def _required(mapping, key):
    if key not in mapping:
        raise MetricError(f"missing required setting: {key}")
    value = mapping[key]
    _resolved(value, key)
    return value


def _choice(settings, key, choices):
    value = _required(settings, key)
    if not isinstance(value, str) or value not in choices:
        raise MetricError(f"{key}: must be one of {sorted(choices)}")
    return value


def _text(settings, key):
    value = _required(settings, key)
    if not isinstance(value, str):
        raise MetricError(f"{key}: must be an explicit nonempty string")
    return value


def _normalization(settings):
    spec = _required(settings, "normalization")
    if not isinstance(spec, dict):
        raise MetricError("normalization: expected an explicit object")
    kind = _choice(spec, "kind", {"identity", "fixed_affine"})
    if kind == "identity":
        if set(spec) != {"kind"}:
            raise MetricError("identity normalization accepts only kind")
        return lambda value: value
    if set(spec) != {"kind", "scale", "offset"}:
        raise MetricError("fixed_affine requires exactly kind, scale, offset")
    scale = _number(_required(spec, "scale"), "normalization.scale")
    offset = _number(_required(spec, "offset"), "normalization.offset")
    if scale == 0:
        raise MetricError("normalization.scale must be nonzero")

    def transform(value):
        return _finite(value * scale + offset, "fixed_affine normalization")

    return transform


def _values(payload, key="values"):
    if key not in payload or not isinstance(payload[key], list):
        raise MetricError(f"{key}: expected a nonempty nested list")

    def walk(value, label):
        if not isinstance(value, list):
            return [_number(value, label)], ()
        if not value:
            raise MetricError(f"{label}: empty values")
        flat = []
        child_shape = None
        for index, child in enumerate(value):
            child_flat, shape = walk(child, f"{label}[{index}]")
            if child_shape is not None and shape != child_shape:
                raise MetricError(f"{label}: ragged shape")
            child_shape = shape
            flat.extend(child_flat)
        return flat, (len(value),) + child_shape

    return walk(payload[key], key)


def _base(prediction, ground_truth, settings):
    if not all(isinstance(value, dict) for value in (prediction, ground_truth, settings)):
        raise MetricError("prediction, ground_truth, and settings must be objects")
    _resolved(settings, "settings")
    authority = _choice(settings, "authority", {"proposal", "code_verified"})
    unit = _text(settings, "unit")
    for label, payload in (("prediction", prediction), ("ground_truth", ground_truth)):
        if payload.get("unit") != unit:
            raise MetricError(f"{label}: unit missing or different from explicit setting")
    transform = _normalization(settings)
    metadata = {"paper_equivalent": False, "authority": authority, "input_unit": unit}
    return transform, metadata


def _mean_nonnegative(values):
    largest = max(values)
    if largest == 0:
        return 0.0
    ratio = math.fsum(value / largest for value in values) / len(values)
    return _finite(largest * ratio, "mean")


def _psnr(prediction, ground_truth, settings, transform, result):
    _choice(settings, "mask_policy", {"all_values"})
    zero_policy = _choice(settings, "zero_mse_policy", {"positive_infinity", "error"})
    _choice(settings, "view_reduction", {"mean_psnr"})
    max_value = _number(_required(settings, "max_value"), "max_value")
    if max_value <= 0:
        raise MetricError("max_value must be positive")
    view_id = _text(prediction, "view_id")
    if _text(ground_truth, "view_id") != view_id:
        raise MetricError("prediction and GT view_id must match")
    pred, pred_shape = _values(prediction)
    gt, gt_shape = _values(ground_truth)
    if pred_shape != gt_shape:
        raise MetricError("prediction and GT shapes must match")
    errors = [
        abs(_finite(transform(p) - transform(g), "PSNR difference"))
        for p, g in zip(pred, gt)
    ]
    largest = max(errors)
    if largest == 0:
        if zero_policy == "error":
            raise MetricError("zero MSE rejected by explicit policy")
        raw, mse = "+inf", 0.0
    else:
        rmse = largest * math.sqrt(
            math.fsum((value / largest) ** 2 for value in errors) / len(errors)
        )
        _finite(rmse, "RMSE")
        mse = _finite(rmse * rmse, "MSE")
        if mse == 0:
            raise MetricError("MSE numerical underflow; nonidentical values are not zero error")
        raw = _finite(20 * (math.log10(max_value) - math.log10(rmse)), "PSNR")
    return dict(
        result, raw=raw, unit="dB", mse=mse, value_count=len(pred), shape=list(pred_shape),
        view_id=view_id, scope="single_view", view_reduction_requested="mean_psnr",
    )


def _points(payload, transform):
    flat, shape = _values(payload, "points")
    if len(shape) != 2 or shape[1] != 3:
        raise MetricError("points must have shape [N, 3]")
    return [tuple(transform(value) for value in flat[i:i + 3]) for i in range(0, len(flat), 3)]


def _nearest(source, target, distance):
    nearest = []
    for point in source:
        best = None
        for other in target:
            delta = [_finite(a - b, "point difference") for a, b in zip(point, other)]
            value = _finite(math.hypot(*delta), "Euclidean distance")
            if distance == "squared_euclidean":
                squared = _finite(value * value, "squared Euclidean distance")
                if value != 0 and squared == 0:
                    raise MetricError("squared Euclidean distance numerical underflow")
                value = squared
            best = value if best is None else min(best, value)
        nearest.append(best)
    return nearest


def _geometry(metric, prediction, ground_truth, settings, transform, result):
    _text(settings, "coordinate_frame")
    _text(settings, "point_sampling")
    distance = _choice(settings, "distance", {"euclidean", "squared_euclidean"})
    # Resolve all choices before doing potentially expensive pairwise work.
    if metric == "cd":
        reduction = _choice(settings, "direction_reduction", {"sum", "mean"})
    else:
        threshold = _number(_required(settings, "threshold"), "threshold")
        if threshold != 0.05:
            raise MetricError("this F-score primitive requires explicit threshold=0.05")
        _choice(settings, "threshold_interpretation", {"euclidean_radius"})
        comparison = _choice(settings, "comparison", {"le", "lt"})
        zero_policy = _choice(settings, "zero_precision_recall", {"zero", "error"})
    pred = _points(prediction, transform)
    gt = _points(ground_truth, transform)
    pred_to_gt = _nearest(pred, gt, distance)
    gt_to_pred = _nearest(gt, pred, distance)
    details = dict(
        result, distance=distance, pred_count=len(pred), gt_count=len(gt),
        pred_to_gt_mean=_mean_nonnegative(pred_to_gt),
        gt_to_pred_mean=_mean_nonnegative(gt_to_pred),
    )
    if metric == "cd":
        means = [details["pred_to_gt_mean"], details["gt_to_pred_mean"]]
        if reduction == "mean":
            raw = _mean_nonnegative(means)
        else:
            raw = _finite(means[0] + means[1], "CD directional sum")
        unit = settings["unit"] if distance == "euclidean" else f"({settings['unit']})^2"
        return dict(
            details, raw=raw, unit=unit, direction_reduction=reduction,
            display_value=_finite(raw / 1e-3, "CD display conversion"),
            table_scale=1e-3,
        )
    effective_threshold = threshold if distance == "euclidean" else threshold * threshold
    hit = (lambda value: value <= effective_threshold) if comparison == "le" else (
        lambda value: value < effective_threshold
    )
    pred_hits = sum(hit(value) for value in pred_to_gt)
    gt_hits = sum(hit(value) for value in gt_to_pred)
    precision = pred_hits / len(pred)
    recall = gt_hits / len(gt)
    if precision + recall == 0:
        if zero_policy == "error":
            raise MetricError("zero precision+recall rejected by explicit policy")
        raw = 0.0
    else:
        raw = 2 * precision * recall / (precision + recall)
    return dict(
        details, raw=raw, unit="ratio", precision=precision, recall=recall,
        pred_hits=pred_hits, gt_hits=gt_hits, threshold=threshold,
        effective_distance_threshold=effective_threshold, comparison=comparison,
        threshold_interpretation="euclidean_radius", definition="directional_hit_fractions",
        display_value=_finite(raw / 1e-2, "F-score display conversion"), table_scale=1e-2,
    )


def _scale(prediction, ground_truth, settings, transform, result):
    representation = _choice(settings, "representation", {"scalar", "vector"})
    pred, pred_shape = _values(prediction)
    gt, gt_shape = _values(ground_truth)
    if len(pred_shape) != 1 or pred_shape != gt_shape:
        raise MetricError("scale requires equal nonempty one-dimensional values")
    if representation == "scalar" and len(pred) != 1:
        raise MetricError("scalar scale representation requires exactly one value")
    difference = [
        _finite(transform(p) - transform(g), "scale difference") for p, g in zip(pred, gt)
    ]
    raw = _finite(math.hypot(*difference), "scale Euclidean distance")
    return dict(result, raw=raw, unit=settings["unit"], representation=representation)


def evaluate(metric: str, prediction: dict, ground_truth: dict, settings: dict) -> dict:
    """Evaluate one synthetic/pre-aligned item with no inferred numerical settings.

    PSNR accepts one view only. Both payloads must name the same ``view_id``;
    the caller must separately validate camera metadata and benchmark eligibility.
    ``fixed_affine`` applies the same explicit transform to prediction and GT;
    per-object min-max normalization and unit conversion are not implemented.
    """
    if not isinstance(metric, str):
        raise MetricError("metric must be a string")
    if metric in {"cov", "mmd"}:
        raise MetricError("not implemented: ID/aggregation unresolved")
    try:
        validate_metric_contract(metric, settings)
    except (AssertionError, ValueError, TypeError) as exc:
        raise MetricError(str(exc)) from exc
    transform, result = _base(prediction, ground_truth, settings)
    result["metric"] = metric
    if metric in _PSNR_METRICS:
        return _psnr(prediction, ground_truth, settings, transform, result)
    if metric == "scale_l2":
        return _scale(prediction, ground_truth, settings, transform, result)
    return _geometry(metric, prediction, ground_truth, settings, transform, result)


def mean_appearance_psnr_30(
    view_results: list[dict], expected_view_ids: list[str], *, infinite_policy: str
) -> dict:
    """Return the arithmetic mean of exactly 30 explicitly identified view PSNRs.

    This helper checks numerical reduction and record correspondence only. It
    neither selects nor verifies random unit-sphere cameras, rendering settings,
    source/GT matching, or paper-equivalent evaluation. Input order must exactly
    match the caller's explicit order; no sorting, dropping, or pooled-MSE
    replacement occurs. Benchmark object aggregation remains unimplemented.
    """
    if not isinstance(infinite_policy, str) or infinite_policy not in {"positive_infinity", "error"}:
        raise MetricError("infinite_policy must explicitly be positive_infinity or error")
    if not isinstance(expected_view_ids, list) or len(expected_view_ids) != 30:
        raise MetricError("expected_view_ids must contain exactly 30 explicit view IDs")
    for view_id in expected_view_ids:
        if not isinstance(view_id, str):
            raise MetricError("expected view IDs must be strings")
        _resolved(view_id, "expected_view_ids")
    if len(set(expected_view_ids)) != 30:
        raise MetricError("expected_view_ids must contain 30 distinct IDs")
    if not isinstance(view_results, list) or len(view_results) != 30:
        raise MetricError("view_results must contain exactly 30 records")
    scores = []
    has_infinity = False
    for index, (record, expected_id) in enumerate(zip(view_results, expected_view_ids)):
        if not isinstance(record, dict):
            raise MetricError(f"view {index}: result must be an object")
        if record.get("view_id") != expected_id:
            raise MetricError(f"view {index}: view ID/order mismatch")
        if record.get("metric") != "appearance_psnr" or record.get("scope") != "single_view":
            raise MetricError(f"view {index}: expected single-view appearance_psnr")
        _choice(record, "authority", {"proposal", "code_verified"})
        if record.get("paper_equivalent") is not False:
            raise MetricError(f"view {index}: paper_equivalent must explicitly be false")
        if record.get("unit") != "dB":
            raise MetricError(f"view {index}: PSNR unit must explicitly be dB")
        raw = record.get("raw")
        if isinstance(raw, str) and raw == "+inf":
            has_infinity = True
        else:
            scores.append(_number(raw, f"view {index}.raw"))
    if has_infinity:
        if infinite_policy == "error":
            raise MetricError("infinite view PSNR rejected by explicit policy")
        mean = "+inf"
    else:
        try:
            mean = _finite(math.fsum(value / 30 for value in scores), "30-view PSNR mean")
        except OverflowError as exc:
            raise MetricError("30-view PSNR mean numerical overflow") from exc
    return {
        "metric": "appearance_psnr", "raw": mean, "unit": "dB",
        "scope": "mean_of_30_views", "view_reduction": "mean_psnr", "view_count": 30,
        "view_ids": list(expected_view_ids), "infinite_policy": infinite_policy,
        "authority": "proposal", "paper_equivalent": False,
    }
