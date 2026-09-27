#!/usr/bin/env python3
"""Read-only verification of this archive; never execute archived installers."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import sys


ORIGINAL_ROOT = "/home/minsujo/Desktop/SH/PHYSx/"
PLAN_RELATIVE = "logs/install-plan-20260921/"
BEFORE_PATH = "local-records/logs/python-foundation-install-20260921/before.json"
FOUNDATION_INPUTS = frozenset(
    {
        "workspace_isolation.py",
        "isolation_probe.py",
        "python-foundation.lock.txt",
        "python-resolved.constraints.txt",
        "python-sparse-candidate.lock.txt",
        "pip-dry-run-initial-report.json",
        "pip-utils3d-dry-run-report.json",
    }
)
RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    prefix + str(number) for prefix in ("COM", "LPT") for number in range(1, 10)
}


def relative_parts(value):
    """Accept canonical, portable relative POSIX paths only."""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("path must be a nonempty string without NUL")
    if "\\" in value or ":" in value:
        raise ValueError("backslashes, drive paths and alternate streams are forbidden")
    path = PurePosixPath(value)
    if path.is_absolute() or PureWindowsPath(value).is_absolute():
        raise ValueError("absolute paths are forbidden")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("empty, dot and parent path components are forbidden")
    if any(part.endswith((" ", ".")) for part in parts):
        raise ValueError("trailing spaces and dots are not portable")
    if any(part.split(".", 1)[0].upper() in RESERVED_NAMES for part in parts):
        raise ValueError("reserved device names are forbidden")
    return parts


def regular_file(bundle, relative):
    """Check every component before opening a regular file inside the bundle."""
    parts = relative_parts(relative)
    candidate = bundle
    for index, part in enumerate(parts):
        candidate = candidate / part
        info = candidate.lstat()
        if stat.S_ISLNK(info.st_mode) or (
            getattr(info, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        ):
            raise ValueError("symlinks and reparse points are forbidden")
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise ValueError("parent component is not a directory")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(bundle)
    except ValueError as error:
        raise ValueError("path escapes the bundle") from error
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("only regular files may be read")
    return resolved


def digest_and_size(path):
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            digest.update(block)
    return digest.hexdigest(), size


def is_digest(value):
    return isinstance(value, str) and re.fullmatch(r"[a-fA-F0-9]{64}", value) is not None


def foundation_path(key):
    """Map only the seven known inputs, including their historical bare names."""
    if not isinstance(key, str):
        raise ValueError("foundation input key must be a string")
    if key in FOUNDATION_INPUTS:
        relative = PLAN_RELATIVE + key
    elif key.startswith(ORIGINAL_ROOT):
        relative = key[len(ORIGINAL_ROOT):]
    else:
        relative = key
    relative_parts(relative)
    expected = {PLAN_RELATIVE + name for name in FOUNDATION_INPUTS}
    if relative not in expected:
        raise ValueError("unexpected foundation input path")
    return "local-records/" + relative


def verify(bundle):
    issues = []
    records = {}
    count = 0
    verified = 0
    foundation_verified = 0

    def issue(scope, message, path=None):
        entry = {"scope": scope, "message": message}
        if path is not None:
            entry["path"] = path
        issues.append(entry)

    try:
        manifest_path = regular_file(bundle, "materials-manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest must be a JSON object")
        if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
            raise ValueError("unsupported manifest schema_version; expected 1")
        entries = manifest.get("files")
        if not isinstance(entries, list) or not entries:
            raise ValueError("manifest files must be a nonempty list")
    except (OSError, ValueError) as error:
        issue("manifest", str(error), "materials-manifest.json")
        entries = []

    count = len(entries)
    for index, entry in enumerate(entries):
        label = "entry " + str(index)
        try:
            if not isinstance(entry, dict):
                raise ValueError("file entry must be a JSON object")
            relative = entry.get("path")
            relative_parts(relative)
            label = relative
            if relative in records:
                raise ValueError("duplicate manifest path")
            records[relative] = entry
            expected_digest = entry.get("sha256")
            expected_size = entry.get("size_bytes")
            if not is_digest(expected_digest):
                raise ValueError("sha256 must contain 64 hexadecimal characters")
            if type(expected_size) is not int or expected_size < 0:
                raise ValueError("size_bytes must be a nonnegative integer")
            path = regular_file(bundle, relative)
            actual_digest, actual_size = digest_and_size(path)
            if actual_size != expected_size:
                raise ValueError("size mismatch: expected %d, got %d" % (expected_size, actual_size))
            if actual_digest != expected_digest.lower():
                raise ValueError("SHA256 mismatch")
            verified += 1
        except (OSError, ValueError) as error:
            issue("file", str(error), label)

    # Together with before.json and its seven inputs, these form the ten
    # required foundation archive files. They are inspected, never imported.
    for filename in ("install_foundation.py", "pip_without_site.py"):
        relative = "local-records/logs/python-foundation-install-20260921/" + filename
        if relative not in records:
            issue("foundation", "required foundation runner is absent from authoritative manifest", relative)

    try:
        if BEFORE_PATH not in records:
            raise ValueError("foundation before.json is absent from authoritative manifest")
        before_path = regular_file(bundle, BEFORE_PATH)
        before = json.loads(before_path.read_text(encoding="utf-8"))
        if not isinstance(before, dict) or not isinstance(before.get("input_sha256"), dict):
            raise ValueError("before.json must contain an input_sha256 object")
        inputs = before["input_sha256"]
        if len(inputs) != len(FOUNDATION_INPUTS):
            issue("foundation", "input_sha256 must contain exactly seven known inputs", BEFORE_PATH)
        seen = set()
        for key, expected_digest in inputs.items():
            label = key
            try:
                relative = foundation_path(key)
                label = relative
                if relative in seen:
                    raise ValueError("duplicate normalized foundation input path")
                seen.add(relative)
                if relative not in records:
                    raise ValueError("foundation input is absent from authoritative manifest")
                if not is_digest(expected_digest):
                    raise ValueError("foundation SHA256 must contain 64 hexadecimal characters")
                path = regular_file(bundle, relative)
                actual_digest, _ = digest_and_size(path)
                if actual_digest != expected_digest.lower():
                    raise ValueError("foundation before.json SHA256 mismatch")
                foundation_verified += 1
            except (OSError, ValueError) as error:
                issue("foundation", str(error), label)
        expected_paths = {"local-records/" + PLAN_RELATIVE + name for name in FOUNDATION_INPUTS}
        for missing in sorted(expected_paths - seen):
            issue("foundation", "required foundation input is missing from before.json", missing)
    except (OSError, ValueError) as error:
        issue("foundation", str(error), BEFORE_PATH)

    return {
        "pass": not issues,
        "count": count,
        "verified_count": verified,
        "foundation_expected_count": len(FOUNDATION_INPUTS),
        "foundation_verified_count": foundation_verified,
        "scope": "materials-manifest.json and foundation before.json input_sha256 only",
        "issues": issues,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Read-only SHA256/size verification of materials beside this script, "
            "plus the seven recorded foundation inputs. Uses the Python standard "
            "library only; does not import or run archived programs, install, "
            "restore, download, access GPUs, or write files. Other historical "
            "hash manifests are not treated as current validators."
        )
    )
    parser.parse_args()
    bundle = Path(__file__).resolve(strict=True).parent
    result = verify(bundle)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
