#!/usr/bin/env python3
"""Regression tests for real mode/IO helpers and runner symbol lifetime."""

import ast
import importlib.util
import json
import sys
import tempfile
import types
from pathlib import Path

from gui_29806_common import atomic_json, corners, execution_plan, internal_exit_payload, validate_modes


HERE = Path(__file__).resolve().parent
RUNNER = HERE / "gui_29806_end_to_end_physics_video.py"
WRAPPER = HERE / "run_gui_29806_gpu0_initialization_isolation_diagnostic.sh"


def expect_error(function, text):
    try:
        function()
    except ValueError as error:
        assert text in str(error)
    else:
        raise AssertionError(f"expected ValueError containing {text!r}")


def test_real_helpers():
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "nested" / "state.json"
        atomic_json(target, {"status": "PASS", "value": 3})
        assert json.loads(target.read_text()) == {"status": "PASS", "value": 3}
        assert not target.with_suffix(".json.tmp").exists()
    assert len(corners({"min": [0, 1, 2], "max": [3, 4, 5]})) == 8


def test_modes_and_actual_plans():
    assert validate_modes() == "default_video"
    assert validate_modes(initialization_diagnostic=True) == "initialization"
    assert validate_modes(initialization_isolation_diagnostic=True) == "isolation"
    assert validate_modes(initialization_isolation_diagnostic=True, diffuse_only_material_diagnostic=True) == "isolation"
    assert validate_modes(gated_recovery_end_to_end=True) == "recovery_video"
    assert "three_door_schedule" in execution_plan("default_video")
    assert "bounded_steps" in execution_plan("initialization")
    assert "visibility_isolation" in execution_plan("isolation", diffuse_only=True)
    assert "diffuse_and_emissive_controls" in execution_plan("isolation", diffuse_only=True)
    assert "recorder" in execution_plan("recovery_video")
    expect_error(lambda: validate_modes(initialization_isolation_diagnostic=True, gated_recovery_end_to_end=True), "mutually exclusive")
    expect_error(lambda: validate_modes(diffuse_only_material_diagnostic=True), "requires initialization isolation")
    failed=internal_exit_payload(status="EXECUTION_OR_API_ERROR",code=1,mode="isolation",plan=execution_plan("isolation"),completed=["stage"],error={"type":"RuntimeError"},last_phase="linked_clones")
    assert failed["python_return_code"]==1 and failed["primary_error"]["type"]=="RuntimeError"
    assert "linked_clones" in failed["unexecuted_phases"] and failed["asset_pass"] is False


def test_runner_definition_lifetime_and_exit_path():
    source = RUNNER.read_text()
    tree = ast.parse(source)
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    local_defs = {node.name for node in ast.walk(main) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "atomic_json" not in local_defs, "atomic_json must remain module-level imported helper"
    assert "corners" not in local_defs, "corners must remain available to every mode"
    assert source.index("validate_modes(") < source.index("SimulationApp("), "reject conflicting flags before Kit startup"
    assert "runner_internal_exit.json" in source
    assert 'return 1' in source and 'internal_exit_payload' in source
    assert 'DIAGNOSTIC_ONLY_ACTIVE_DOOR_MOTION_NOT_EXPECTED' in source
    invalid_branch = source.index('return finish(21,"DIFFUSE_ONLY_PREPHYSICS_INVALID"')
    assert invalid_branch < source.index("SimulationManager.setup_simulation"), "invalid prephysics must stop before physics setup"
    wrapper = WRAPPER.read_text()
    assert wrapper.index('((rc==0)) || fail isaac_child') < wrapper.index("rg -qx 'INITIALIZATION_ISOLATION_DIAGNOSTIC_COMPLETE'")
    assert wrapper.index("rg -qx 'INITIALIZATION_ISOLATION_DIAGNOSTIC_COMPLETE'") < wrapper.index("printf '0\\n' >\"$LOG_DIR/wrapper_exit_code.txt\"")


def test_actual_main_entry_and_error_exit_for_every_mode():
    """Run the real main() to its input gate with only Isaac imports stubbed."""
    created = []
    closed = []
    class FakeApp:
        def __init__(self, *args, **kwargs):
            created.append((args, kwargs))
        def close(self):
            closed.append(True)
    modules = {}
    for name in ("isaacsim", "carb", "omni", "omni.kit", "omni.kit.app",
                 "omni.timeline", "omni.usd", "warp", "isaacsim.core",
                 "isaacsim.core.simulation_manager", "omni.kit.viewport",
                 "omni.kit.viewport.utility", "pxr"):
        modules[name] = types.ModuleType(name)
    modules["isaacsim"].SimulationApp = FakeApp
    modules["carb"].settings = types.SimpleNamespace(
        get_settings=lambda: types.SimpleNamespace(set=lambda *args: None))
    modules["isaacsim.core.simulation_manager"].PhysxScene = object
    modules["isaacsim.core.simulation_manager"].SimulationManager = object
    modules["omni.kit.viewport.utility"].frame_viewport_prims = lambda *args: None
    modules["omni.kit.viewport.utility"].get_active_viewport = lambda: None
    for name in ("Gf", "Sdf", "Usd", "UsdGeom", "UsdLux", "UsdPhysics", "UsdShade"):
        setattr(modules["pxr"], name, types.SimpleNamespace())
    originals = {name: sys.modules.get(name) for name in modules}
    try:
        sys.modules.update(modules)
        for parent, child in (("omni", "kit"), ("omni.kit", "app"),
                              ("omni", "timeline"), ("omni", "usd")):
            setattr(modules[parent], child, modules[parent + "." + child])
        spec = importlib.util.spec_from_file_location("gui_29806_runner_under_test", RUNNER)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        with tempfile.TemporaryDirectory() as directory:
            for flags, expected_mode in (
                ([], "default_video"),
                (["--initialization-diagnostic"], "initialization"),
                (["--initialization-isolation-diagnostic"], "isolation"),
                (["--initialization-isolation-diagnostic", "--diffuse-only-material-diagnostic"], "isolation"),
                (["--gated-recovery-end-to-end"], "recovery_video"),
            ):
                run_dir = Path(directory) / (expected_mode + ("_diffuse" if len(flags) == 2 else ""))
                original_argv = sys.argv
                sys.argv = [str(RUNNER), "--root", directory, "--input-usd", str(run_dir / "missing.usda"),
                            "--input-urdf", str(run_dir / "missing.urdf"), "--run-dir", str(run_dir),
                            "--capture-size", "1280x720", *flags]
                try:
                    assert runner.main() == 1
                finally:
                    sys.argv = original_argv
                result = json.loads((run_dir / "runner_internal_exit.json").read_text())
                assert result["mode"] == expected_mode
                assert result["status"] == "EXECUTION_OR_API_ERROR"
                assert result["primary_error"]["type"] == "FileNotFoundError"
                assert result["unexecuted_phases"] and result["asset_pass"] is False
                assert (run_dir / "physics_gui_report.json").is_file()
            assert len(created) == len(closed) == 5
            original_argv = sys.argv
            sys.argv = [str(RUNNER), "--root", directory, "--input-usd", "missing.usda",
                        "--input-urdf", "missing.urdf", "--run-dir", str(Path(directory) / "invalid"),
                        "--capture-size", "1280x720", "--initialization-isolation-diagnostic",
                        "--gated-recovery-end-to-end"]
            try:
                expect_error(runner.main, "mutually exclusive")
            finally:
                sys.argv = original_argv
            assert len(created) == 5, "invalid flag combination must stop before Kit startup"
            class FailingApp:
                def __init__(self, *args, **kwargs):
                    raise RuntimeError("synthetic startup failure")
            runner.SimulationApp = FailingApp
            startup_dir = Path(directory) / "startup_failure"
            original_argv = sys.argv
            sys.argv = [str(RUNNER), "--root", directory, "--input-usd", "missing.usda",
                        "--input-urdf", "missing.urdf", "--run-dir", str(startup_dir),
                        "--capture-size", "1280x720"]
            try:
                assert runner.main() == 1
            finally:
                sys.argv = original_argv
            startup = json.loads((startup_dir / "runner_internal_exit.json").read_text())
            assert startup["status"] == "ISAAC_APP_STARTUP_ERROR"
            assert startup["primary_error"]["message"] == "synthetic startup failure"
            assert startup["unexecuted_phases"] == execution_plan("default_video")
    finally:
        for name, previous in originals.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


if __name__ == "__main__":
    test_real_helpers()
    test_modes_and_actual_plans()
    test_runner_definition_lifetime_and_exit_path()
    test_actual_main_entry_and_error_exit_for_every_mode()
    print("GUI_29806_RUNNER_PATH_TESTS_PASS")
