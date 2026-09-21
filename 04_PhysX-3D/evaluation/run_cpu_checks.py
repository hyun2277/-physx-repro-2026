#!/usr/bin/env python3
"""Run only small synthetic checks in a read-only, offline, GPU-free sandbox."""
import datetime
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import traceback
import uuid

ROOT = Path("/home/minsujo/Desktop/SH/PHYSx")
CODE = Path(__file__).resolve().parent
PYTHON = ROOT / "envs/physxgen/bin/python"
sys.path.insert(0, str(CODE))
from physx_eval.common import file_hash, write_new_json


def timestamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def worker(run):
    import socket
    import unittest
    from physx_eval.manifest import build_manifest
    if os.environ.get("PHYSX_CPU_ISOLATED") != "1" or list(Path("/dev").glob("nvidia*")):
        raise RuntimeError("expected CPU-only sandbox")
    if any(name != "lo" for _, name in socket.if_nameindex()):
        raise RuntimeError("network isolation is missing")
    versions = {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
                "third_party_packages_required": [], "gpu_visible_nodes": [],
                "network_interfaces": socket.if_nameindex()}
    write_new_json(run / "versions.json", versions)
    print("CPU synthetic checks; Python " + platform.python_version(), flush=True)
    print("No third-party/model imports; network and GPU devices hidden", flush=True)
    prefix = "repro-records/04_PhysX-3D/평가규약/2026-09-21_초안/"
    manifest = build_manifest(ROOT, prefix + "test-input-gt-correspondence.csv",
                              "sources/physx-4f54e750a309/val_test_list.npy")
    write_new_json(run / "official-test-manifest.json", manifest)
    write_new_json(run / "manifest-summary.json", {"items": len(manifest["items"]),
                   "unique_ids": len({item["object_id"] for item in manifest["items"]}),
                   "all_bindings_unresolved": all(not item["bindings"] for item in manifest["items"]),
                   "source": manifest["source"], "paper_equivalent": False})

    class Result(unittest.TextTestResult):
        def startTest(self, test):
            self.starts = getattr(self, "starts", {})
            self.starts[test.id()] = timestamp()
            super().startTest(test)

        def stopTest(self, test):
            self.records = getattr(self, "records", [])
            failed = any(t is test or getattr(t, "test_case", None) is test
                         for t, _ in self.failures + self.errors)
            self.records.append({"test": test.id(), "started_at": self.starts[test.id()],
                                 "ended_at": timestamp(), "status": "failed" if failed else "passed"})
            super().stopTest(test)

    suite = unittest.defaultTestLoader.discover(str(CODE / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(suite)
    forbidden = sorted(name for name in sys.modules if name.split(".")[0] in {"torch", "numpy", "kaolin", "transformers"})
    report = {"tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "skipped": len(result.skipped), "tests": getattr(result, "records", []),
              "unexpected_imports": forbidden, "paper_equivalent": False,
              "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    write_new_json(run / "checks.json", report)
    return 0 if result.wasSuccessful() and not forbidden else 1


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        return worker(Path(sys.argv[2]))
    if len(sys.argv) != 1:
        raise ValueError("No options: this runner only executes the fixed CPU checks")
    os.umask(0o077)
    run_id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
    run = ROOT / "logs/evaluation-cpu-20260921" / run_id
    run.mkdir(parents=True)
    temporary = run / "temporary"
    for name in ["shm", "runtime", "cache", "config", "data", "state", "fixtures"]:
        (temporary / name).mkdir(parents=True)
    env = {"HOME": os.environ["HOME"], "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
           "TMPDIR": str(temporary), "TMP": str(temporary), "TEMP": str(temporary),
           "XDG_RUNTIME_DIR": str(temporary / "runtime"), "XDG_CACHE_HOME": str(temporary / "cache"),
           "XDG_CONFIG_HOME": str(temporary / "config"), "XDG_DATA_HOME": str(temporary / "data"),
           "XDG_STATE_HOME": str(temporary / "state"), "CUDA_VISIBLE_DEVICES": "",
           "PHYSX_CPU_ISOLATED": "1", "PHYSX_ROOT": str(ROOT),
           "PHYSX_TEST_TMP": str(temporary / "fixtures")}
    argv = ["/usr/bin/bwrap", "--die-with-parent", "--new-session", "--unshare-user", "--unshare-pid",
            "--unshare-ipc", "--unshare-uts", "--unshare-net", "--cap-drop", "ALL", "--clearenv",
            "--ro-bind", "/", "/", "--bind", str(run), str(run),
            "--bind", str(temporary), "/tmp", "--bind", str(temporary), "/var/tmp",
            "--proc", "/proc", "--ro-bind", "/proc/sys", "/proc/sys", "--dev", "/dev",
            "--bind", str(temporary / "shm"), "/dev/shm", "--chdir", str(CODE)]
    for key, value in env.items():
        argv += ["--setenv", key, value]
    argv += ["--", str(PYTHON), "-I", "-B", "-S", "-u", str(Path(__file__).resolve()), "--worker", str(run)]
    started = timestamp()
    write_new_json(run / "command.json", {"argv": argv, "cwd": str(CODE), "started_at": started,
                   "scope": "CPU synthetic checks and existing split metadata only", "gpu_stage": False})
    hashes = {str(p.relative_to(CODE)): file_hash(p) for p in sorted(CODE.rglob("*"))
              if p.is_file() and p.suffix in {".py", ".json"} and "evidence" not in p.parts}
    write_new_json(run / "code-hashes.json", hashes)
    code, error = 1, None
    try:
        with (run / "stdout.log").open("x") as out, (run / "stderr.log").open("x") as err:
            proc = subprocess.run(argv, env=env, cwd=CODE, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
            code = proc.returncode
    except Exception as exc:
        error = type(exc).__name__ + ": " + str(exc)
    finally:
        write_new_json(run / "result.json", {"started_at": started, "ended_at": timestamp(),
                       "exit_code": code, "error": error, "paper_equivalent": False,
                       "log_directory": str(run), "gpu_stage": False, "protection_fallback": False})
    print(json.dumps({"exit_code": code, "log_directory": str(run)}, ensure_ascii=False), flush=True)
    return code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
