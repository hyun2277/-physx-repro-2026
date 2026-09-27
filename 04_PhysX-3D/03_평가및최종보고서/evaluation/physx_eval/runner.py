"""Append-only CPU item attempts with pinned contracts and explicit retries."""
import contextlib
import datetime
import fcntl
import math
from pathlib import Path
import platform
import sys
import traceback
import uuid

from .common import (ContractError, digest, file_hash, local_path, read_json,
                     require, write_new_json)
from .manifest import validate_manifest
from .mapping import validate_binding
from .metrics import MetricError, evaluate


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def run_id():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]


def code_hash():
    directory = Path(__file__).parent
    return digest({p.name: file_hash(p) for p in sorted(directory.glob("*.py"))})


def configuration(config):
    require(isinstance(config, dict), "config must be a JSON object")
    require(config.get("schema_version") == 1, "unsupported config schema")
    require(config.get("claim") == "proposal_cpu_check", "paper-equivalent evaluation is not available")
    require(config.get("failure_mode") == "stop", "failure mode must explicitly be stop")
    require(config.get("execution_scope") == "synthetic_fixture", "actual/full evaluation is disabled in this version")
    require(config.get("aggregation") == {"mode": "disabled", "duplicate_policy": None,
                                         "failure_policy": None, "denominator": None},
            "final aggregation is blocked: unresolved policies/denominator")
    require(isinstance(config.get("metrics"), dict) and config["metrics"], "explicit metrics required")
    return config


def run_session(root, manifest, config, session_path, *, retry_failed=False):
    """A successful metric is reusable only under the same immutable session contract.

    Validate provenance even on reuse. A failure stops later work, and retries need
    explicit consent from the caller. No shell/model/renderer invocation occurs.
    """
    validate_manifest(root, manifest)
    require(type(retry_failed) is bool, "retry_failed must be an explicit boolean")
    configuration(config)
    require(manifest["kind"] == "synthetic_fixture", "only synthetic CPU runs are enabled")
    session = local_path(root, session_path)
    session.mkdir(parents=True, exist_ok=True)
    with (session / ".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ContractError("session already running; no duplicate execution") from exc
        return _run_locked(root, manifest, config, session, retry_failed)


def _run_locked(root, manifest, config, session, retry_failed):
    contract = {"manifest_sha256": digest(manifest), "config_sha256": digest(config),
                "code_sha256": code_hash(), "python": platform.python_version(),
                "paper_equivalent": False}
    header = session / "session.json"
    if header.exists():
        require(read_json(header) == contract, "resume contract changed; create a new session")
        require(digest(read_json(session / "manifest.json")) == contract["manifest_sha256"],
                "stored manifest snapshot differs or is incomplete")
        require(digest(read_json(session / "config.json")) == contract["config_sha256"],
                "stored config snapshot differs or is incomplete")
    else:
        require(not (session / "items").exists(), "orphan item records without session contract")
        write_new_json(header, contract)
        write_new_json(session / "manifest.json", manifest)
        write_new_json(session / "config.json", config)
    invocation = session / "invocations" / run_id()
    invocation.mkdir(parents=True)
    started = now()
    write_new_json(invocation / "command.json", {
        "operation": "run_session", "argv": sys.argv, "python": sys.executable,
        "version": platform.python_version(), "started_at": started,
        "retry_failed": retry_failed, "contract": contract})
    outcomes = []
    stop = False
    for item in manifest["items"]:
        for metric, settings in config["metrics"].items():
            if stop:
                outcomes.append({"item_key": item["item_key"], "metric": metric, "status": "not_attempted"})
                continue
            require(metric.isidentifier(), "invalid metric name")
            base = session / "items" / item["item_key"] / metric
            previous = sorted(base.glob("attempt-*")) if base.exists() else []
            latest = None
            prior_state = None
            if previous:
                last = previous[-1]
                try:
                    latest = read_json(last / "result.json")
                    completion = read_json(last / "completion.json")
                    require(isinstance(latest, dict) and isinstance(completion, dict),
                            "result/completion must be JSON objects")
                    require(completion["result_sha256"] == file_hash(last / "result.json"), "result checksum mismatch")
                    require(latest["contract"] == contract, "attempt contract mismatch")
                    for key in ["item_key", "object_id", "source_index"]:
                        require(type(latest.get(key)) is type(item[key]) and latest[key] == item[key],
                                "attempt item identity mismatch")
                    require(latest.get("metric") == metric, "attempt metric mismatch")
                    prior_state = latest["status"]
                    require(prior_state in {"success", "blocked", "failed"}, "invalid attempt status")
                    if prior_state == "success":
                        score = latest.get("score")
                        require(type(latest.get("exit_code")) is int and latest["exit_code"] == 0 and
                                latest.get("paper_equivalent") is False and isinstance(score, dict)
                                and score.get("metric") == metric and score.get("paper_equivalent") is False
                                and score.get("authority") == settings.get("authority") and "raw" in score,
                                "invalid successful result")
                        require((type(score["raw"]) in {float, int} and math.isfinite(score["raw"]))
                                or (metric.endswith("psnr") and score["raw"] == "+inf"
                                    and settings.get("zero_mse_policy") == "positive_infinity"),
                                "invalid score value in successful result")
                except (ValueError, OSError, KeyError):
                    prior_state = "interrupted_or_corrupt"
            if previous and prior_state != "success" and not retry_failed:
                outcomes.append({"item_key": item["item_key"], "metric": metric,
                                 "status": "retry_required", "previous_state": prior_state})
                stop = True
                continue
            attempt = base / (f"attempt-{len(previous) + 1:06d}-" + run_id())
            # Validate before trusting a previously successful result; write any
            # changed/missing artifact failure into a new attempt, never the old one.
            binding_error = None
            try:
                prediction, gt = validate_binding(root, item, metric, settings)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                binding_error = exc
            if prior_state == "success" and binding_error is None:
                outcomes.append({"item_key": item["item_key"], "metric": metric,
                                 "status": "reused_success", "attempt": str(previous[-1].relative_to(session))})
                continue
            attempt.mkdir(parents=True)
            attempt_start = now()
            write_new_json(attempt / "command.json", {"operation": "physx_eval.metrics.evaluate",
                           "metric": metric, "item_key": item["item_key"], "object_id": item["object_id"],
                           "source_index": item["source_index"], "started_at": attempt_start,
                           "python": platform.python_version(), "contract": contract,
                           "previous_state": prior_state})
            result = {"item_key": item["item_key"], "object_id": item["object_id"],
                      "source_index": item["source_index"], "metric": metric,
                      "started_at": attempt_start, "contract": contract, "paper_equivalent": False}
            with (attempt / "stdout.log").open("x", buffering=1) as out, (attempt / "stderr.log").open("x", buffering=1) as err:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    try:
                        if binding_error is not None:
                            raise binding_error
                        score = evaluate(metric, prediction, gt, settings)
                        result.update(status="success", exit_code=0, score=score)
                        print("CPU item metric completed; proposal check only", flush=True)
                    except Exception as exc:
                        result.update(status="blocked" if isinstance(exc, (ContractError, MetricError)) else "failed",
                                      exit_code=2 if isinstance(exc, (ContractError, MetricError)) else 1,
                                      error_type=type(exc).__name__, error=str(exc))
                        traceback.print_exc()
                        stop = True
            result["ended_at"] = now()
            write_new_json(attempt / "result.json", result)
            write_new_json(attempt / "completion.json", {"result_sha256": file_hash(attempt / "result.json")})
            outcomes.append({"item_key": item["item_key"], "metric": metric, "status": result["status"],
                             "attempt": str(attempt.relative_to(session))})
    statuses = [r["status"] for r in outcomes]
    summary = {"started_at": started, "ended_at": now(), "exit_code": 2 if stop else 0,
               "paper_equivalent": False, "claim": "proposal_cpu_check", "outcomes": outcomes,
               "counts": {name: statuses.count(name) for name in
                          ["success", "reused_success", "blocked", "failed", "retry_required", "not_attempted"]},
               "declared_item_metrics": len(outcomes),
               "aggregation": {"status": "blocked", "reason": "duplicate/failure policy and denominator unresolved",
                               "final_score": None}}
    write_new_json(invocation / "result.json", summary)
    return summary
