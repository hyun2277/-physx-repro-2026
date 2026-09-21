"""Strict JSON and project-local file operations."""
import hashlib
import json
import math
from pathlib import Path


class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key: " + key)
            result[key] = value
        return result

    def bad_constant(value):
        raise ContractError("non-finite JSON constant: " + value)

    def finite_float(value):
        result = float(value)
        require(math.isfinite(result), "non-finite JSON number")
        return result

    return json.loads(Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=pairs, parse_constant=bad_constant, parse_float=finite_float)


def write_new_json(path, value):
    """Exclusive creation: existing run records are never replaced."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(canonical(value).decode("utf-8") + "\n")
        stream.flush()
        import os
        os.fsync(stream.fileno())


def local_path(root, path):
    root = Path(root).resolve(strict=True)
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    require(resolved != root and root in resolved.parents, "path escapes project root")
    return resolved


def checked_ref(root, ref):
    require(isinstance(ref, dict), "missing file reference")
    require(isinstance(ref.get("path"), str) and ref["path"], "missing reference path")
    expected = ref.get("sha256")
    require(isinstance(expected, str) and len(expected) == 64
            and all(c in "0123456789abcdef" for c in expected), "missing/invalid SHA256")
    path = local_path(root, ref["path"])
    require(path.is_file(), "referenced file missing: " + ref["path"])
    require(file_hash(path) == expected, "file hash mismatch: " + ref["path"])
    return path


def resolved(value):
    """Configuration placeholders cannot accidentally become configured values."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip()) and value.strip().casefold() not in {
            "unresolved", "unknown", "tbd", "todo", "none", "null", "미확정", "?"}
    if isinstance(value, dict):
        return bool(value) and all(resolved(v) for v in value.values())
    if isinstance(value, list):
        return bool(value) and all(resolved(v) for v in value)
    if isinstance(value, float):
        return math.isfinite(value)
    return isinstance(value, (int, bool))
