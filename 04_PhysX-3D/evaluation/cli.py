#!/usr/bin/env python3
"""Use with python -I -B -S. No install, data acquisition, or model commands."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from physx_eval.common import canonical, local_path, read_json, write_new_json
from physx_eval.manifest import build_manifest, validate_manifest
from physx_eval.mapping import validate_binding


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("manifest")
    for name in ["csv", "npy", "output"]:
        make.add_argument("--" + name, required=True)
    check = sub.add_parser("validate")
    for name in ["manifest", "config", "output"]:
        check.add_argument("--" + name, required=True)
    run = sub.add_parser("synthetic-run")
    for name in ["manifest", "config", "session"]:
        run.add_argument("--" + name, required=True)
    run.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    if args.command == "manifest":
        result = build_manifest(args.root, args.csv, args.npy)
        write_new_json(local_path(args.root, args.output), result)
        print(canonical({"manifest": args.output, "items": len(result["items"]), "paper_equivalent": False}).decode())
        return 0
    manifest = read_json(local_path(args.root, args.manifest))
    config = read_json(local_path(args.root, args.config))
    if args.command == "synthetic-run":
        from physx_eval.runner import run_session
        result = run_session(args.root, manifest, config, args.session, retry_failed=args.retry_failed)
        print(canonical(result).decode())
        return result["exit_code"]
    result = validate_manifest(args.root, manifest)
    rows = []
    if not isinstance(config, dict) or not isinstance(config.get("metrics"), dict) or not config["metrics"]:
        raise ValueError("explicit metrics required")
    for item in manifest["items"]:
        for metric, settings in config["metrics"].items():
            try:
                validate_binding(args.root, item, metric, settings)
                status = {"status": "structurally_valid", "error": None}
            except (ValueError, OSError, KeyError, TypeError) as exc:
                status = {"status": "blocked", "error": str(exc)}
            rows.append({"item_key": item["item_key"], "metric": metric, **status})
    result["bindings"] = rows
    result["exit_code"] = 2 if any(r["status"] == "blocked" for r in rows) else 0
    result["semantic_data_validation"] = "not_established"
    write_new_json(local_path(args.root, args.output), result)
    print(canonical({"rows": result["rows"], "exit_code": result["exit_code"], "paper_equivalent": False}).decode())
    return result["exit_code"]


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        raise SystemExit(2)
