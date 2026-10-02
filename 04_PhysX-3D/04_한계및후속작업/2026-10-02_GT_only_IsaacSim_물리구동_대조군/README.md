# GT-only Isaac Sim 물리 drive 대조군 — 첫 실행 기록

이 폴더는 GT `finaljson/group_info/partseg`로 이미 생성된 USD만 읽는 대조군 실행기와 첫 실제 실행 기록을 보관한다. 자동 예측군의 mesh, physics, group, parent, axis, origin, range는 읽거나 사용하지 않았다.

## 실행 결과

실행 ID `20261002T081820Z-gt-only-physics-control`은 GPU 1 (`GPU-843dced4-ee97-dbb8-36c9-343fe13b7647`, driver 595.84)에서 시작했다. 10163의 composed `Physics=physx` stage는 revolute joint 1개, articulation root 1개, rigid body 3개, collider(instance proxy 포함) 2개라는 사전 조건을 통과했다.

그러나 첫 timeline step 뒤 Isaac은 반복해서 `No simulation registered, please make sure to register a simulation.`을 기록했다. 따라서 drive target을 보낸 뒤의 상태는 유효한 physics simulation 결과가 아니며, 10163·29806의 range 내 5개 목표/10회 왕복/3회 초기화, range 밖 시험, 29354 fixed 시험은 **미실행**으로 판정한다. 29806의 문별 독립 구동도 시작하지 않았다. 짧은 physics 영상도 만들지 않았다.

이 실패는 GT 관절 또는 자동 예측군의 실패가 아니다. 기존 USD variant에 scene registration이 되지 않은 Isaac stage setup 문제다. GT 값으로 관절을 새로 만들거나, transform animation으로 대체하거나, joint/axis/range를 보정하지 않았다.

## 통제 조건과 범위

실행기는 physical GPU 1만 사용하고 P2P/multi-GPU를 비활성화한다. 기존 importer USD의 `Physics=physx` (10163·29806) 및 `Physics=physics` (29354)을 열며, source URDF/USD는 저장하지 않는다. drive는 existing `PhysicsDriveAPI:angular`의 position/force authoring을 사용하도록 준비했으며, test 설정은 USD가 author한 finite stiffness/damping/maxForce를 결과에 기록하도록 한다. importer에서 사용한 공통 mass/inertia/collision은 “통제된 실험 설정”으로만 분리 기록한다.

자동 예측군 상태는 이전 감사대로 10163·29806 `INTERPRETATION_BLOCKED`, 29354 `NO_DEPLOYABLE_JOINT_SPEC`이며, 이 실행기는 자동 예측군 USD 변환을 시도하지 않는다.

## 다음 최소 조치

`No simulation registered`의 원인을 Isaac의 physics-scene lifecycle과 current composed payload stage로 한정해 점검해야 한다. scene registration이 명시적으로 확인되기 전에는 이 runner를 재실행하거나 drive/contact/영상 시험을 하지 않는다.

## 10163 runtime PhysicsScene 등록 후 drive 시도 (20261002T083648Z)

PhysicsScene registration smoke가 통과한 뒤 10163만 다시 실행했다. runtime/session-layer
`/World/GTOnlyRuntimePhysicsScene`을 Isaac Sim 6.1.0 `SimulationManager`에 등록하고
step counter가 `2 -> 3`으로 증가했다. 이어 composed `Physics=physx` stage에서 revolute
joint 1개, articulation root 1개, rigid body 3개, collider 2개를 확인했다. 따라서 이번
시도에서는 이전의 `No simulation registered`가 재발하지 않았다.

그러나 첫 초기화 target과 이어지는 range 내 command에서 PhysX가
`PxArticulationJointReducedCoordinate::setDriveTarget(): ... illegal ...
PxSceneFlag::eENABLE_DIRECT_GPU_API`를 기록했다. GPU direct API가 활성화된 scene에서
USD `PhysicsDriveAPI:angular` target을 author하는 현재 control 방식이 허용되지 않는다는
명시적 엔진 오류다. drive target은 PhysX에 적용되지 않았으므로 joint position/velocity,
rigid-body transform, contact 상태, range 밖 clamp, 5 target/10 왕복/3 초기화의 유효한
결과는 없다. 이 실행은 **GT 관절 실패나 AI 예측 실패가 아니라, GPU PhysX control API
호환성 실패**로 기록한다.

영상은 만들지 않았다. 실제 drive state가 없는데 transform animation으로 대체하면 안 되기
때문이다. 29806·29354·자동 예측군은 실행하지 않았다. 다음 조치는 설치된 Isaac 6.1
tensor `ArticulationView.set_dof_position_targets` 경로가 direct-GPU scene의 공식 control
경로인지 별도로 검증하는 것이며, 이 기록에서는 재시도하지 않는다. 같은 오류를 반복하지
않도록 현재 USD `PhysicsDriveAPI` runner는 CUDA physics device에서 target authoring 전에
명시적으로 중단하도록 보호했다.
