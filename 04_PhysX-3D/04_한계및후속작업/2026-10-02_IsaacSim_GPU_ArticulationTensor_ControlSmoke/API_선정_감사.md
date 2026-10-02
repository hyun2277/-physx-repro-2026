# GPU direct articulation 제어 API 감사

## 판정

10163 GT-only 대조군의 GPU 1 PhysX direct scene에는 **Isaac Sim 6.1.0의
`SimulationManager.get_physics_simulation_view()`가 만든 Warp `omni.physics.tensors`
articulation view**를 선정했다. 이 API는 positional target을 backend에 전달하고, 현재
joint state를 tensor로 읽는다. USD attribute를 실행 중에 author하지 않는다.

- 공식 API: [Robot Simulation Snippets](https://docs.isaacsim.omniverse.nvidia.com/6.1.0/python_scripting/robots_simulation.html)는 `Articulation.set_dof_position_targets()` 및 DOF state read API를 제시한다.
- 설치된 tensor API: `tools/isaac-sim/extscache/omni.physics.tensors-110.3.2+110.3.0.lx64.r.cp312.u7f4/omni/physics/tensors/api.py:1643-1660`은 rotational DOF readback이 radians임을 명시하고, `1794-1825`는 position target이 instantaneous state write가 아닌 controller target임을 명시한다.
- Isaac 6.1 manager: `tools/isaac-sim/exts/isaacsim.core.simulation_manager/isaacsim/core/simulation_manager/impl/simulation_manager.py:778-786`은 initialized Warp view를 생성하며, `878-893`은 `get_physics_simulation_view()`를 제공한다.
- GPU direct 제약: 설치된 NVIDIA policy helper `.../isaacsim.robot.policy.examples/.../interactive/utils.py:50-66`은 CUDA device가 Fabric/PhysX direct-GPU API를 켜며 실행 중 `setDriveTarget` USD 변경이 불가하다고 명시한다.

## 대안 비교

| 경로 | 근거 | 이번 선택 여부 |
|---|---|---|
| CUDA PhysX + tensor articulation target | direct-GPU scene에서 USD target authoring 없이 target/state를 전달·조회 | 선택 |
| CPU PhysX + runtime USD `PhysicsDriveAPI` target | installed helper가 device를 `cpu` 또는 `cuda:0`로 복원 가능한 별도 조건임을 명시 | 미선택: GPU 1 direct 대조군과 device/Fabric/direct-API 조건이 다름 |

CPU 전환이 공식적으로 가능한 device 선택임은 확인했지만, 그 실행은 GPU direct trial과 다른
simulation condition이다. 비교 없이 두 경로를 섞지 않는다.

## 초기화 순서

1. `Physics=physx` composed variant를 연다.
2. session layer에 runtime-only `PhysxScene`을 author하고 `SimulationManager.setup_simulation(..., device="cuda:0")` 및 `initialize_physics()`를 호출한다.
3. manager step counter가 증가한 뒤 `SimulationManager.get_physics_simulation_view()`를 얻는다.
4. 해당 view의 `create_articulation_view()` → metatype DOF name/index → position/velocity/target readback 순서로 조회한다.
5. 한 개의 bounded target만 tensor API로 요청하고 manager step 뒤 state를 다시 읽는다.

별도 `tensors.create_simulation_view(..., stage_id=-1)`를 만들면 attached stage를 찾지 못했다.
따라서 manager가 초기화한 view만 사용한다.

## control smoke 결과

실행 ID `20261002T084601Z-10163-gpu-tensor-control`에서 runtime PhysicsScene,
articulation 1개, DOF `gt_C_1` 1개, target request/readback, manager counter `2→3→4`,
전후 finite state를 확인했다. rotational limits는 `[-1.57079637, 1.57079637]` radians다.
이는 target 전달 경로의 smoke 통과일 뿐, joint response, range 준수, 반복성, collider/contact,
actual motion을 판정하지 않는다.

이전 시도 두 건은 PyTorch frontend 미포함 및 detached tensor-stage initialization으로 각각
실패했다. 둘 다 GT/URDF/USD/PhysicsScene/AI output 실패로 해석하지 않는다.
