# 29806 GT-only 통제된 물성 조건의 관절 동작 검증

**판정: PASS.** 이는 PhysXNet GT `finaljson/group_info/partseg` 기반 URDF→USD 변환과 Isaac Sim 물리 구동의 대조군이다. PhysX-3D AI 자동 예측 성공 증거가 아니며, generated mesh·raw physics·predicted group·axis·parent·range를 읽거나 보완하지 않았다.

`Physics=physx` composed stage에서 회전 관절 3개(`gt_C_1`~`gt_C_3`), articulation root 1개, rigid body 11개, collider 8개를 확인했다. 세 관절의 GT range는 모두 `[-π, 0]` rad였으며, 각 관절을 하나씩 독립 구동했다. 각 trial은 초기화 3회(각 60 step), range 안 target 5개와 10회 왕복(2,400 recorded step), upper limit + 0.2 rad의 range 밖 요청(60 step)으로 구성했다.

GPU 1만 `CUDA_VISIBLE_DEVICES=1`로 사용했고, Isaac에서는 `cuda:0`으로 보인다. P2P/multi-GPU는 사용하지 않았다. GPU direct PhysX mode 때문에 실행 중 USD `PhysicsDriveAPI` target이나 stage transform/keyframe은 author하지 않고, initialized Warp `omni.physics.tensors` articulation view의 position target API만 사용했다.

세 관절 모두 실제 state가 유한했고, limits + 0.05 rad 범위에 남았으며, active response span은 각각 약 2.1734, 2.1600, 2.1465 rad였다. 다른 두 DOF의 settled-neutral 기준 최대 drift는 모두 0.000108 rad 이하였고, root link의 최대 translation drift는 0.000018 m 이하였다. 이는 이 **통제된 GT 대조군**에서 문 하나를 구동할 때 다른 관절 DOF와 fixed root가 의도하지 않게 같이 구동되지 않았음을 뜻한다. 실제 링크-문 대응 또는 실제 접촉력 정확도는 여기서 평가하지 않았다.

공통 실험 물성은 session layer에서 physics 초기화 전에만 적용했다: 각 rigid body 질량 1.0 kg, 대각 관성 `(0.1, 0.1, 0.1)` kg·m², identity principal axes. 이는 GT나 AI가 예측한 물성이 아니라 안정적인 변환기·시뮬레이터 smoke를 위한 통제 조건이다. 기존 importer collider와 drive stiffness/damping/max force는 유지했다. 의도적인 contact pair가 없어 collision API 존재·finite transform만 검사했고 contact force는 주장하지 않는다.

`29806_gt_only_physics_joint_state_trace.mp4`는 실제 logged tensor target과 joint-position record에서 만든 10.2초 H.264 **physics state-trace**다. transform을 강제로 덮어쓴 애니메이션이나 AI가 문을 여닫는다는 시연이 아니다. 전체 per-step report는 Git 밖 staging의 `physics_drive_report.json`(SHA256은 `summary.json` 참조)에 보존한다.

미검증: 자동 예측 joint 변환, AI 축·원점·range 정확도, mesh/GT 대응, contact-force 정확도, 29354, 실제 제조 적합성.
