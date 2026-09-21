"""Validate prepared CPU artifacts and their provenance; never infer correspondence."""
import math

from .common import checked_ref, read_json, require, resolved

PSNR = {"appearance_psnr", "density_psnr", "affordance_psnr", "description_psnr"}
SUPPORTED = PSNR | {"scale_l2", "cd", "fscore"}


def validate_settings(metric, settings):
    require(metric in SUPPORTED, "metric unimplemented: ID/kinematics aggregation unresolved")
    require(isinstance(settings, dict), "missing metric settings")
    require(settings.get("authority") in {"proposal", "code_verified"},
            "settings authority must be explicit; paper equivalence is unavailable")
    common = ["unit", "normalization", "alignment", "context"]
    for key in common:
        require(resolved(settings.get(key)), "missing/unresolved setting: " + key)
    require(settings["alignment"] == "already_aligned", "implicit alignment is forbidden")
    ctx = settings["context"]
    require(isinstance(ctx, dict), "context must be an object")
    for key in ["coordinate_frame", "normalization_id"]:
        require(resolved(ctx.get(key)), "missing context: " + key)
    if metric in PSNR:
        for key in ["camera_set_id", "camera_sampling", "camera_parameters", "view_ids",
                    "image_shape", "color_space", "background", "mask_policy"]:
            require(resolved(ctx.get(key)), "missing camera/map context: " + key)
        require(isinstance(ctx["view_ids"], list) and all(isinstance(v, str) for v in ctx["view_ids"])
                and len(set(ctx["view_ids"])) == len(ctx["view_ids"]), "invalid view IDs")
        # This version scores one prepared view, not a 30-view/object aggregate.
        require(len(ctx["view_ids"]) == 1, "multi-view aggregation not implemented")
        require(ctx["mask_policy"] == settings.get("mask_policy"), "mask policies differ")
        require(isinstance(ctx["camera_parameters"], dict), "camera parameters must be explicit")
        for key in ["extrinsic", "intrinsic", "resolution", "near", "far", "convention"]:
            require(resolved(ctx["camera_parameters"].get(key)), "missing camera parameter: " + key)
        camera = ctx["camera_parameters"]
        for key, size in [("extrinsic", 4), ("intrinsic", 3)]:
            matrix = camera[key]
            require(isinstance(matrix, list) and len(matrix) == size and all(
                isinstance(row, list) and len(row) == size and all(
                    type(value) in {int, float} and math.isfinite(value) for value in row)
                for row in matrix), "invalid camera matrix: " + key)
        shape = ctx["image_shape"]
        require(isinstance(shape, list) and len(shape) in {2, 3} and
                all(type(n) is int and n > 0 for n in shape), "invalid image shape")
        require(camera["resolution"] == [shape[1], shape[0]], "resolution/image shape mismatch")
        require(type(camera["near"]) in {int, float} and type(camera["far"]) in {int, float}
                and 0 < camera["near"] < camera["far"], "invalid camera clipping planes")
    if metric in {"density_psnr", "affordance_psnr", "description_psnr"}:
        require(ctx.get("part_correspondence") == "explicit_file_map", "part mapping required")
    if metric == "description_psnr":
        for key in ["question_type", "question_text", "question_target_part", "gt_map_definition",
                    "text_encoder_revision"]:
            require(resolved(ctx.get(key)), "missing question context: " + key)
    if metric in {"cd", "fscore"}:
        require(settings.get("coordinate_frame") == ctx["coordinate_frame"], "coordinate frame mismatch")
        require(resolved(settings.get("point_sampling")), "point sampling is unresolved")
    return settings


def validate_binding(root, item, metric, settings):
    validate_settings(metric, settings)
    binding = item["bindings"].get(metric)
    require(isinstance(binding, dict), "input/GT binding is missing")
    input_ref = binding.get("input")
    checked_ref(root, input_ref)
    require(input_ref.get("object_id") == item["object_id"], "input object ID mismatch")
    require(resolved(input_ref.get("view_id")), "input view must be explicit")
    payloads = []
    for role in ["prediction", "ground_truth"]:
        path = checked_ref(root, binding.get(role))
        artifact = read_json(path)
        require(isinstance(artifact, dict), "artifact must be a JSON object")
        require(artifact.get("schema_version") == 1 and artifact.get("role") == role,
                "artifact schema/role mismatch")
        for key in ["item_key", "object_id", "source_index"]:
            require(type(artifact.get(key)) is type(item[key]) and artifact[key] == item[key],
                    role + " identity mismatch: " + key)
        require(artifact.get("input_sha256") == input_ref["sha256"], "artifact refers to different input")
        require(artifact.get("input_view_id") == input_ref["view_id"], "input view mismatch")
        require(artifact.get("context") == settings["context"], "camera/unit/question context mismatch")
        payload = artifact.get("payload")
        require(isinstance(payload, dict), "missing numeric payload")
        require(payload.get("unit") == settings["unit"], "payload unit mismatch")
        if metric in PSNR:
            require(payload.get("view_id") in settings["context"]["view_ids"], "evaluation view mismatch")
            def shape_of(value):
                if not isinstance(value, list):
                    return []
                require(bool(value), "empty map")
                children = [shape_of(child) for child in value]
                require(all(child == children[0] for child in children), "ragged map")
                return [len(value)] + children[0]
            require(shape_of(payload.get("values")) == settings["context"]["image_shape"],
                    "payload/image shape mismatch")
        payloads.append(payload)
    if metric in {"density_psnr", "affordance_psnr", "description_psnr"}:
        parts = binding.get("parts")
        require(isinstance(parts, list) and parts, "missing part correspondence")
        labels, indices = set(), set()
        for part in parts:
            require(isinstance(part, dict), "part correspondence must be a JSON object")
            label, index = part.get("label"), part.get("parts_index")
            require(isinstance(label, str) and label not in labels, "duplicate/invalid part label")
            require(type(index) is int and index >= 0 and index not in indices, "duplicate/invalid part index")
            labels.add(label); indices.add(index)
            mesh = checked_ref(root, part.get("mesh"))
            require(mesh.name == part.get("mesh_filename"), "part mesh filename mismatch")
        annotation = read_json(checked_ref(root, binding.get("annotation")))
        require(isinstance(annotation, dict), "annotation must be a JSON object")
        require(annotation.get("object_id") == item["object_id"], "annotation object mismatch")
        require(isinstance(annotation.get("parts"), list), "annotation parts missing")
        require(all(isinstance(part, dict) for part in annotation["parts"]), "annotation parts must be objects")
        for part in parts:
            index = part["parts_index"]
            require(index < len(annotation["parts"]) and
                    str(annotation["parts"][index].get("label")) == part["label"],
                    "annotation label/index mismatch")
        require(len(parts) == len(annotation["parts"]), "incomplete part correspondence")
        if metric == "description_psnr":
            require(settings["context"]["question_target_part"] in labels, "question target part missing")
    return tuple(payloads)
