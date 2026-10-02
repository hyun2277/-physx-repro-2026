"""Register and step a runtime-only PhysX scene; it never drives a joint or saves the input USD."""
import argparse
import hashlib
import json
import traceback
from pathlib import Path

from isaacsim import SimulationApp


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--input-usd", type=Path, required=True)
    parser.add_argument("--log-dir", type=Path, required=True)
    args = parser.parse_args()
    args.log_dir.mkdir(parents=True, exist_ok=True)
    experience = args.root / (
        "repro-records/04_PhysX-3D/04_한계및후속작업/"
        "2026-10-02_IsaacSim_PhysicsScene_등록Smoke/isaac_physics_scene_smoke.kit"
    )
    app = SimulationApp(
        {
            "headless": True,
            "active_cuda_gpus": [0],  # CUDA_VISIBLE_DEVICES=1 maps CUDA 0 to physical GPU 1.
            "physics_gpu": 0,
            "multi_gpu": False,
            "extra_args": [
                "--/renderer/multiGpu/enabled=false",
                "--/renderer/multiGpu/autoEnable=false",
            ],
        },
        experience=str(experience),
    )
    print("PHYSICS_SCENE_SMOKE_APP_READY", flush=True)
    try:
        import omni.timeline
        import omni.usd
        from isaacsim.core.simulation_manager import PhysxScene, SimulationManager
        from pxr import Sdf, Usd, UsdPhysics

        context = omni.usd.get_context()
        context.open_stage(str(args.input_usd))
        app.update()
        app.update()
        print("PHYSICS_SCENE_SMOKE_STAGE_OPENED", flush=True)
        stage = context.get_stage()
        root = stage.GetDefaultPrim()
        if not root or not root.IsValid():
            raise RuntimeError("opened USD has no valid default prim")
        physics_variants = root.GetVariantSets().GetVariantSet("Physics")
        if physics_variants.IsValid() and "physx" in physics_variants.GetVariantNames():
            physics_variants.SetVariantSelection("physx")
        app.update()
        print("PHYSICS_SCENE_SMOKE_VARIANT_SELECTED", flush=True)

        preexisting = [str(prim.GetPath()) for prim in stage.Traverse() if prim.IsA(UsdPhysics.Scene)]
        old_target = stage.GetEditTarget()
        session_layer = stage.GetSessionLayer()
        stage.SetEditTarget(Usd.EditTarget(session_layer))
        runtime_scene = PhysxScene("/World/GTOnlyRuntimePhysicsScene")
        runtime_scene.set_gravity((0.0, 0.0, -9.81))
        runtime_scene.set_dt(1.0 / 60.0)
        stage.SetEditTarget(old_target)
        app.update()
        print("PHYSICS_SCENE_SMOKE_RUNTIME_SCENE_AUTHORED", flush=True)

        scene_paths_before = [scene.path for scene in SimulationManager.get_physics_scenes()]
        engines_before = SimulationManager.get_available_physics_engines()
        SimulationManager.setup_simulation(dt=1.0 / 60.0, device="cuda:0")
        SimulationManager.initialize_physics()
        print("PHYSICS_SCENE_SMOKE_MANAGER_INITIALIZED", flush=True)
        steps_before = SimulationManager.get_num_physics_steps()
        simulating_before = SimulationManager.is_simulating()
        timeline = omni.timeline.get_timeline_interface()
        timeline.play()
        app.update()
        SimulationManager.step(steps=1, update_fabric=False)
        app.update()
        steps_after_step = SimulationManager.get_num_physics_steps()
        timeline.stop()
        app.update()
        steps_after_stop = SimulationManager.get_num_physics_steps()
        report = {
            "scope": "Runtime/session-layer PhysX registration and one no-drive step only; input USD was not saved or modified.",
            "input_usd": str(args.input_usd),
            "input_usd_sha256": sha256(args.input_usd),
            "variant": physics_variants.GetVariantSelection() if physics_variants.IsValid() else None,
            "preexisting_physics_scene_paths": preexisting,
            "session_layer_identifier": session_layer.identifier,
            "runtime_scene_path": runtime_scene.path,
            "runtime_scene_in_session_layer": bool(session_layer.GetPrimAtPath(Sdf.Path(runtime_scene.path))),
            "scene_paths_before_manual_initialization": scene_paths_before,
            "available_engines_before_manual_initialization": engines_before,
            "physics_device": SimulationManager.get_physics_sim_device(),
            "timeline_played": True,
            "is_simulating_before_step": simulating_before,
            "physics_steps_before": steps_before,
            "physics_steps_after_manual_step": steps_after_step,
            "physics_steps_after_stop": steps_after_stop,
            "physics_step_advanced": steps_after_step > steps_before,
            "success_rule": "SimulationManager registered a PhysX scene and one no-drive physics step increased the official physics-step counter.",
        }
        (args.log_dir / "physics_scene_registration_report.json").write_text(json.dumps(report, indent=2) + "\n")
        if not report["runtime_scene_in_session_layer"] or not report["physics_step_advanced"]:
            raise RuntimeError("PhysicsScene registration smoke did not satisfy its success rule")
        print("PHYSICS_SCENE_SMOKE_RUNTIME_SCENE_REGISTERED", flush=True)
        print("PHYSICS_SCENE_SMOKE_STEP_ADVANCED", flush=True)
        print("PHYSICS_SCENE_SMOKE=PASS", flush=True)
        return 0
    except BaseException:
        traceback.print_exc()
        raise
    finally:
        app.close()


if __name__ == "__main__":
    raise SystemExit(main())
