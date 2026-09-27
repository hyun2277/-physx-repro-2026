"""Shared metric-setting contracts used before binding and during calculation."""

import math

from .common import require, resolved

PSNR = {"appearance_psnr", "density_psnr", "affordance_psnr", "description_psnr"}
SUPPORTED = PSNR | {"scale_l2", "cd", "fscore"}


def validate_metric_contract(metric, settings):
    """Validate settings required by both preflight and metric primitives.

    Input/camera binding rules remain in :mod:`mapping`; this function owns
    numerical metric prerequisites so a missing field cannot pass preflight
    and fail later (notably ``scale_l2.representation``).
    """
    require(metric in SUPPORTED, "metric unimplemented: ID/kinematics aggregation unresolved")
    require(isinstance(settings, dict), "missing metric settings")
    require(settings.get("authority") in {"proposal", "code_verified"},
            "settings authority must be explicit; paper equivalence is unavailable")
    for key in ("unit", "normalization"):
        require(resolved(settings.get(key)), "missing/unresolved setting: " + key)
    if metric == "scale_l2":
        require(settings.get("representation") in {"scalar", "vector"},
                "missing/unresolved setting: representation")
    if metric in {"cd", "fscore"}:
        for key in ("coordinate_frame", "point_sampling", "distance"):
            require(resolved(settings.get(key)), "missing/unresolved setting: " + key)
        require(settings["distance"] in {"euclidean", "squared_euclidean"},
                "distance must be euclidean or squared_euclidean")
        if metric == "cd":
            require(settings.get("direction_reduction") in {"sum", "mean"},
                    "missing/unresolved setting: direction_reduction")
        else:
            threshold = settings.get("threshold")
            require(type(threshold) in {int, float} and math.isfinite(float(threshold)),
                    "missing/unresolved setting: threshold")
            require(float(threshold) == 0.05, "this F-score primitive requires explicit threshold=0.05")
            require(settings.get("threshold_interpretation") == "euclidean_radius",
                    "threshold interpretation must be euclidean_radius")
            require(settings.get("comparison") in {"le", "lt"},
                    "comparison must be le or lt")
            require(settings.get("zero_precision_recall") in {"zero", "error"},
                    "zero precision/recall policy is unresolved")
    return settings
