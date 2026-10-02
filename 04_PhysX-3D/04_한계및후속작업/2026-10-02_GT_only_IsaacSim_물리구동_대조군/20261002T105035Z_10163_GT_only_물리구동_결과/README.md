# 10163 GT-only 통제된 물성 조건의 관절 동작 검증

**판정: PASS.** 이것은 GT `finaljson/group_info/partseg`에서 이미 만들어진 `Physics=physx` USD의 Isaac Sim 변환기·시뮬레이터 대조군이다. PhysX-3D 자동 예측 결과가 아니며, generated mesh/physics/group/axis/parent/range를 사용하지 않았다.

GPU 1의 CUDA PhysX direct mode에서 session-layer PhysicsScene을 등록한 뒤, `SimulationManager.get_physics_simulation_view()`의 Warp `omni.physics.tensors` articulation view로 target을 요청했다. 실행 중 USD `PhysicsDriveAPI` target이나 stage transform을 author하지 않았다.

- articulation/DOF: 1 / `gt_C_1`
- GT range: `[-1.57079637, 1.57079637]` rad
- in-range targets: `[-1.2, -0.6, 0.0, 0.6, 1.2]` rad
- 10 round trips: 2,400 recorded steps
- initialization: 3 × 60 = 180 recorded steps
- out-of-range request: upper limit + 0.2 rad, 60 recorded steps
- observed in-range response span: 2.38392794 rad
- finite state: true; limit plus 0.05 rad tolerance: true

The importer-authored drive had stiffness `1.74532926`, damping `0.17453292`, and max force `2000`. Before physics initialization, the runtime/session layer applied the controlled common material condition to each rigid body: mass `1.0 kg`, diagonal inertia `(0.1, 0.1, 0.1) kg·m²`, and identity principal axes. Existing colliders were retained; there was no intentional contact pair, so contact-force correctness is not asserted.

`10163_gt_only_physics_joint_state_trace.mp4` is a 10.3-second H.264 visualization of the **logged actual physics joint state and tensor target requests**. It is a state-trace video, not a transform-animation or a rendered claim that the AI predicted a working hinge.

Not validated: automatic predicted-joint conversion, axis/origin/range accuracy of any AI output, contact-force accuracy, 29806, 29354, and real-world manufacturing suitability. Full per-step state remains outside Git at `/home/minsujo/Desktop/SH/PHYSx/staging/gt-only-isaac-tensor-drive-20261002T105035Z-10163-tensor-drive/physics_drive_report.json` (SHA256 `7e09c7d658f37ffa15761f0d37b2a7c97eb9a9759b41b8e6597a5a412144f610`).
