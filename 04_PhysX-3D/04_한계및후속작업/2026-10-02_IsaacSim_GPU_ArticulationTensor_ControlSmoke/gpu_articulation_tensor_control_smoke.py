"""GT-only one-joint tensor-control smoke; never authors transforms or USD drive targets."""
import argparse
import hashlib
import json
import math
import traceback
from pathlib import Path

from isaacsim import SimulationApp


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def values(value):
    return value.numpy().tolist()


def flatten(value):
    if isinstance(value, list):
        for item in value:
            yield from flatten(item)
    else:
        yield float(value)


def all_finite(value) -> bool:
    return all(math.isfinite(item) for item in flatten(values(value)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--input-usd", type=Path, required=True)
    parser.add_argument("--log-dir", type=Path, required=True)
    args = parser.parse_args()
    args.log_dir.mkdir(parents=True, exist_ok=True)
    experience = args.root / (
        "repro-records/04_PhysX-3D/04_한계및후속작업/"
        "2026-10-02_IsaacSim_GPU_ArticulationTensor_ControlSmoke/"
        "isaac_gpu_articulation_tensor_smoke.kit"
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
    print("GPU_TENSOR_CONTROL_APP_READY", flush=True)
    try:
        import omni.usd
        import warp as wp
        from isaacsim.core.simulation_manager import PhysxScene, SimulationManager
        from pxr import Sdf, Usd, UsdPhysics

        context = omni.usd.get_context()
        context.open_stage(str(args.input_usd))
        app.update(); app.update()
        stage = context.get_stage()
        root = stage.GetDefaultPrim()
        variants = root.GetVariantSets().GetVariantSet("Physics")
        if not variants.IsValid() or "physx" not in variants.GetVariantNames():
            raise RuntimeError("expected Physics=physx variant is unavailable")
        variants.SetVariantSelection("physx")
        app.update()
        print("GPU_TENSOR_CONTROL_STAGE_READY", flush=True)

        old_target = stage.GetEditTarget()
        session_layer = stage.GetSessionLayer()
        stage.SetEditTarget(Usd.EditTarget(session_layer))
        runtime_scene = PhysxScene("/World/GTOnlyRuntimePhysicsScene")
        runtime_scene.set_gravity((0.0, 0.0, -9.81))
        runtime_scene.set_dt(1.0 / 60.0)
        stage.SetEditTarget(old_target)
        app.update()
        if not session_layer.GetPrimAtPath(Sdf.Path(runtime_scene.path)):
            raise RuntimeError("runtime PhysicsScene was not authored in session layer")
        SimulationManager.setup_simulation(dt=1.0 / 60.0, device="cuda:0")
        SimulationManager.initialize_physics()
        steps_before = SimulationManager.get_num_physics_steps()
        SimulationManager.step(steps=1, update_fabric=False)
        app.update()
        steps_after_scene = SimulationManager.get_num_physics_steps()
        if steps_after_scene <= steps_before:
            raise RuntimeError("PhysicsScene registration did not advance")
        print("GPU_TENSOR_CONTROL_PHYSICS_READY", flush=True)

        roots = [str(prim.GetPath()) for prim in stage.Traverse() if prim.HasAPI(UsdPhysics.ArticulationRootAPI)]
        if len(roots) != 1:
            raise RuntimeError(f"expected exactly one articulation root, got {roots}")
        # Isaac Sim 6.1 creates the attached Warp tensor view during
        # SimulationManager.initialize_physics(); do not construct another view with stage_id=-1.
        sim_view = SimulationManager.get_physics_simulation_view()
        if sim_view is None:
            raise RuntimeError("SimulationManager did not expose its initialized Warp physics view")
        articulation = sim_view.create_articulation_view(roots)
        if articulation.count != 1 or articulation.max_dofs != 1:
            raise RuntimeError(f"expected one articulation/one DOF, got count={articulation.count}, max_dofs={articulation.max_dofs}")
        meta = articulation.get_metatype(0)
        if meta.dof_count != 1 or len(meta.dof_names) != 1:
            raise RuntimeError(f"expected one actual DOF, got dof_count={meta.dof_count}, names={meta.dof_names}")
        dof_index = meta.dof_indices[meta.dof_names[0]]
        limits = articulation.get_dof_limits()
        position_before = articulation.get_dof_positions()
        velocity_before = articulation.get_dof_velocities()
        targets_before = articulation.get_dof_position_targets()
        if not all(all_finite(item) for item in (limits, position_before, velocity_before, targets_before)):
            raise RuntimeError("non-finite tensor state before target request")
        lower, upper = (float(x) for x in values(limits)[0][dof_index])
        current = float(values(position_before)[0][dof_index])
        # This is one small bounded request in radians; it is a target, never an instantaneous state write.
        request = min(upper - 1e-4, max(lower + 1e-4, current + 0.01))
        target_values = values(targets_before)
        target_values[0][dof_index] = request
        targets = wp.array(target_values, dtype=wp.float32, device=targets_before.device)
        indices = wp.array([0], dtype=wp.uint32, device=targets.device)
        articulation.set_dof_position_targets(targets, indices)
        print("GPU_TENSOR_CONTROL_TARGET_REQUESTED", flush=True)
        target_readback = articulation.get_dof_position_targets()
        step_before_target = SimulationManager.get_num_physics_steps()
        SimulationManager.step(steps=1, update_fabric=False)
        app.update()
        step_after_target = SimulationManager.get_num_physics_steps()
        position_after = articulation.get_dof_positions()
        velocity_after = articulation.get_dof_velocities()
        if step_after_target <= step_before_target:
            raise RuntimeError("step did not advance after tensor target request")
        if not all(all_finite(item) for item in (target_readback, position_after, velocity_after)):
            raise RuntimeError("non-finite tensor state after target request")
        report = {
            "scope": "GT-only single bounded tensor target-control smoke; no transform authoring, keyframe animation, range sweep, round-trip, video, 29806, 29354, or generated-output asset.",
            "input_usd": str(args.input_usd),
            "input_usd_sha256": sha256(args.input_usd),
            "physics_variant": variants.GetVariantSelection(),
            "runtime_scene": {"path": runtime_scene.path, "layer": "session; not saved"},
            "physics_device": SimulationManager.get_physics_sim_device(),
            "simulation_step_counter": [steps_before, steps_after_scene, step_before_target, step_after_target],
            "tensor_api": {"module": "omni.physics.tensors", "frontend": "Warp via SimulationManager.get_physics_simulation_view", "backend": "physx"},
            "articulation_root_paths": roots,
            "articulation_count": articulation.count,
            "max_dofs": articulation.max_dofs,
            "dof": {"name": meta.dof_names[0], "index": dof_index, "limits_radians": [lower, upper]},
            "state_before": {"position_radians": values(position_before), "velocity_radians_per_sec": values(velocity_before), "target_radians": values(targets_before)},
            "target_request_radians": request,
            "target_readback_radians": values(target_readback),
            "state_after": {"position_radians": values(position_after), "velocity_radians_per_sec": values(velocity_after)},
            "finite": True,
            "success_rule": "session PhysicsScene advanced; one articulated DOF was discovered; tensor target request/readback and a subsequent physics step completed with finite state.",
            "not_a_motion_validation": "No response-span threshold is applied in this smoke. Five-target, round-trip, reset, range-out, contact, and video tests remain unexecuted.",
        }
        (args.log_dir / "gpu_articulation_tensor_control_report.json").write_text(json.dumps(report, indent=2) + "\n")
        print("GPU_TENSOR_CONTROL_ARTICULATION_DISCOVERED", flush=True)
        print("GPU_TENSOR_CONTROL_STATE_READBACK", flush=True)
        print("GPU_TENSOR_CONTROL=PASS", flush=True)
        return 0
    except BaseException:
        traceback.print_exc()
        raise
    finally:
        app.close()


if __name__ == "__main__":
    raise SystemExit(main())
