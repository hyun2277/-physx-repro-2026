# Isaac Sim GPU direct articulation tensor-control smoke

10163 GT-only USD의 composed `Physics=physx` variant를 session-layer `PhysicsScene`과 함께 열고, Isaac Sim 6.1.0의 `omni.physics.tensors` PhysX backend로 한 개 DOF의 bounded position target을 요청하는 최소 smoke다. GPU direct API에서 실행 중 USD `PhysicsDriveAPI` attribute를 author하지 않는다.

`omni.physics.tensors.create_simulation_view("torch", backend="physx")` → `create_articulation_view()` → metatype의 DOF 이름·인덱스 확인 → `get_dof_positions()`/`get_dof_velocities()` → `set_dof_position_targets()` → `SimulationManager.step()` → state readback 순서를 사용한다. rotational DOF tensor state와 target은 radians이며, USD rotational limit/target은 degrees일 수 있으므로 혼용하지 않는다.

통과는 runtime PhysicsScene step, articulation/DOF 발견, bounded target request/readback, 다음 step과 유한 state만 뜻한다. 5개 target, 왕복, reset, range 밖, 접촉, 영상은 실행하지 않는다. 결과는 GT-only simulator-control evidence이며 AI prediction 결과가 아니다.

`SimulationManager`를 CUDA로 구성한 PhysX direct-GPU scene에서 runtime USD DriveAPI target authoring이 불가하다는 설치된 Isaac policy helper의 설명과 NVIDIA 6.1 robot-control documentation을 근거로 tensor interface를 선택했다. CPU PhysX + USD DriveAPI 전환은 GPU direct scene과 다른 device/fabric/direct-API 조건을 도입하므로, GPU-1 GT control 목적의 이 smoke에는 선택하지 않았다.
