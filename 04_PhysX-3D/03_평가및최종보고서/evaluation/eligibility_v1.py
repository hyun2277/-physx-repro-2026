"""Eligibility state machine for public-materials independent evaluation v1."""

VALID_STATUSES = {
    "COMPLETE_NOW", "READY_FOR_INFERENCE", "NEEDS_SHAPENET_FILE", "NEEDS_CONDITIONING",
    "MAPPING_UNRESOLVED", "SOURCE_MISSING", "UNSAFE_OR_UNKNOWN_MEMORY",
}


def classify_status(*, source_ok, mapping_ok, texture_ok, conditioning_ok, generated_ok, memory_known):
    """Return one explicit blocker/success state without inventing missing assets."""
    if not source_ok:
        return "SOURCE_MISSING"
    if not mapping_ok:
        return "MAPPING_UNRESOLVED"
    if not texture_ok:
        return "NEEDS_SHAPENET_FILE"
    if not conditioning_ok:
        return "NEEDS_CONDITIONING"
    if generated_ok:
        return "COMPLETE_NOW"
    if not memory_known:
        return "UNSAFE_OR_UNKNOWN_MEMORY"
    return "READY_FOR_INFERENCE"
