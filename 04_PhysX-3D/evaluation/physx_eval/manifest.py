"""Ordered manifests. Duplicate IDs remain distinct source rows, not weights."""
import ast
from collections import Counter
import csv
import struct
from pathlib import Path

from .common import checked_ref, file_hash, local_path, require

NPY_SHA256 = "b2cc94a8a8ae1c8f2f5ca17de35f784d4bd220723223449141bea1dfab7122fc"


def source_test_ids(path):
    require(file_hash(path) == NPY_SHA256, "official split hash differs from reviewed source")
    raw = Path(path).read_bytes()
    require(raw[:8] == b"\x93NUMPY\x01\x00", "unsupported NPY header")
    length = struct.unpack("<H", raw[8:10])[0]
    meta = ast.literal_eval(raw[10:10 + length].decode("latin1"))
    require(meta == {"descr": "<U5", "fortran_order": False, "shape": (2000,)},
            "unexpected split shape/type")
    data = raw[10 + length:].decode("utf-32-le")
    require(len(data) == 10000, "truncated split")
    return [data[i:i + 5].rstrip("\0") for i in range(5000, 10000, 5)]


def make_rows(ids, source_start):
    seen = Counter()
    rows = []
    for index, object_id in enumerate(ids):
        require(isinstance(object_id, str) and object_id, "object ID must remain a string")
        seen[object_id] += 1
        rows.append({"item_key": f"test-{index:06d}", "test_index": index,
                     "source_index": source_start + index, "object_id": object_id,
                     "occurrence": seen[object_id], "bindings": {}})
    return rows


def build_manifest(root, csv_path, npy_path):
    csv_path = local_path(root, csv_path)
    npy_path = local_path(root, npy_path)
    ids = source_test_ids(npy_path)
    with csv_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    expected = make_rows(ids, 1000)
    require(len(rows) == len(expected), "CSV test length differs")
    for row, entry in zip(rows, expected):
        for field, key in [("test_index_0based", "test_index"),
                           ("source_index_0based", "source_index"),
                           ("same_id_occurrence_1based", "occurrence"),
                           ("object_id", "object_id")]:
            require(row[field] == str(entry[key]), "CSV order/identity differs from official NPY")
    manifest = {"schema_version": 1, "kind": "official_test", "paper_equivalent": False,
                "duplicate_aggregation_policy": None,
                "source": {"csv": {"path": str(csv_path.relative_to(Path(root).resolve())),
                                     "sha256": file_hash(csv_path)},
                           "npy": {"path": str(npy_path.relative_to(Path(root).resolve())),
                                     "sha256": NPY_SHA256}}, "items": expected}
    validate_manifest(root, manifest)
    return manifest


def validate_manifest(root, manifest):
    require(isinstance(manifest, dict), "manifest must be a JSON object")
    require(manifest.get("schema_version") == 1, "unsupported manifest schema")
    require(manifest.get("paper_equivalent") is False, "paper equivalence is not established")
    require(manifest.get("duplicate_aggregation_policy") is None,
            "duplicate aggregation remains unresolved; this version does not aggregate")
    kind = manifest.get("kind")
    items = manifest.get("items")
    require(isinstance(items, list) and bool(items), "empty manifest")
    require(all(isinstance(item, dict) for item in items), "manifest items must be objects")
    if kind == "official_test":
        source = manifest.get("source", {})
        npy = checked_ref(root, source.get("npy"))
        csv_path = checked_ref(root, source.get("csv"))
        ids = source_test_ids(npy)
        with csv_path.open(newline="", encoding="utf-8") as stream:
            csv_rows = list(csv.DictReader(stream))
        require(len(csv_rows) == 1000, "source CSV length changed")
        seen = Counter()
        for i, (row, object_id) in enumerate(zip(csv_rows, ids)):
            seen[object_id] += 1
            require(row["object_id"] == object_id and row["test_index_0based"] == str(i)
                    and row["source_index_0based"] == str(1000 + i)
                    and row["same_id_occurrence_1based"] == str(seen[object_id]), "source CSV order mismatch")
        start = 1000
    elif kind == "synthetic_fixture":
        require(len(items) <= 32, "synthetic fixture limited to 32 rows")
        ids = [item.get("object_id") for item in items]
        start = 0
    else:
        raise ValueError("manifest kind must be explicit")
    expected = make_rows(ids, start)
    require(len(items) == len(expected), "manifest length differs from source")
    for item, original in zip(items, expected):
        for key in ("item_key", "test_index", "source_index", "object_id", "occurrence"):
            require(type(item.get(key)) is type(original[key]) and item[key] == original[key],
                    "manifest order/identity mismatch: " + key)
        require(isinstance(item.get("bindings"), dict), "bindings must be an explicit mapping")
    return {"rows": len(items), "unique_ids": len(set(ids)), "kind": kind,
            "duplicate_aggregation_policy": None, "paper_equivalent": False}
