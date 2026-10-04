# 29806 초기화 recovery 기반 gated end-to-end 준비

이 기록은 **GT-only 변환기·Isaac Sim 대조군**이며 PhysX-3D 자동 예측 성공 기록이 아니다. Host physics와 영상은 이번 변경에서 실행하지 않았다.

## 네 실행의 phase 비교

| 실행 | 확인 범위 | 판정 |
|---|---|---|
| A 정적 mapping | physics 0 step, source↔clone 및 픽셀, 사람 화면 | `STATIC_MAPPING_AUTOMATION_AND_HUMAN_PASS` |
| B 첫 빠른 physics | 450 records, 세 DOF/body 회전 반응 | `INVALID_FAST_VISUAL_AND_INACTIVE_DOF_DRIFT` |
| C continuity 보완 | 초기화 뒤 manager step 2, 빨강 0 px, schedule/recorder 미시작 | `VISUAL_CONTINUITY_GATE_FAIL_AFTER_INITIALIZE_GT_C_1_MISSING` |
| D initialization-only | `initialize_physics()` 전 0, 직후 2; tensor view 뒤 after-init pixel FAIL | `INITIALIZATION_DIAGNOSTIC_CONFIRMED_FAIL_AT_MANAGER_STEP_2` |

D는 after-initialize USD transform과 tensor state를 저장한 뒤 pixel FAIL 분기로 종료했다. 별도 step 1/2/5/10은 실행하지 않았고 completion marker가 없는 이유도 이 분기다.

## 확인된 경계와 남은 후보

`SimulationManager.initialize_physics()` 호출에서 manager counter가 0→2로 바뀌었다. tensor view는 그 뒤 생성됐다. authored USD의 root와 세 body1, linked clone world transform은 초기화 전후 translation/rotation delta가 모두 0이었다. 반면 tensor는 C1/C2/C3가 각각 -0.002488/-0.004029/-0.005303 rad, velocity -0.0511/-0.0905/-0.1324 rad/s였고 viewport red는 48,950 px에서 0 px로 사라졌다. 이 값은 유한하며 큰 body 폭발을 나타내지 않는다. 따라서 첫 차이는 authored USD가 아니라 runtime/Fabric presentation에서 관측됐지만, occlusion·constraint/collision correction·presentation sync 중 하나로 아직 확정하지 않는다. object/depth ID는 기존 실행에 없다.

closed target은 세 관절 모두 0 rad로 고정했다. URDF origin, USD body authored transform과 localPos0 일치, localPos1=0, identity local rotations, Y axis, 상한 0, tensor radian convention이 같은 결론을 지지한다. 명시적인 authored drive target은 없다. GT stiffness/damping/effort/velocity limit은 바꾸지 않는다.

## 새 단일 runner

`run_gui_29806_gpu0_gated_recovery_end_to_end.sh`는 after-init pixel FAIL을 숨기지 않고 audit PNG/JSON에 남긴다. 이후 세 DOF의 0 rad target 전체 vector를 매 step 보내며 최대 300 step recovery를 수행한다. 1/2/5/10/30/60/120/180/240/300 및 최초 안정 지점에서 tensor/body/clone/pixel 상태를 남긴다.

Recovery는 각 DOF absolute error ≤0.01 rad, |velocity|≤0.05 rad/s 30 step 연속, pixel baseline ratio ≥0.20, center shift ≤40 px, root translation ≤1e-4 m, orientation ≤0.002 rad, finite state, body escape 없음, clone xform/timeSample author 0을 모두 만족해야 통과한다. 300 step 안에 못 맞추면 `INITIALIZATION_RECOVERY_FAIL`로 recorder와 active schedule 전에 종료한다.

통과하면 닫힘 화면을 실제 1.5초 더 유지하고 recorder를 시작한다. 각 문은 닫힘 1.5초, smoothstep 열기 3초, 열린 상태 1.5초, smoothstep 닫기 3초, 0.5~5초 조건부 settle 순으로 구동된다. 영상은 31.5~45초, initialize 이후 recovery·hold를 포함한 완료 구간은 33.5~51.5초로 예상한다(Isaac startup/preflight 제외). inactive excursion ≤0.002 rad 및 closed absolute error ≤0.01 rad 기준은 유지한다.

## 경고

Kit log의 `Ill-formed SdfPath <>`와 shutdown의 `Unexpected reference count of 2`는 원문과 위치를 보존했다. 저장소 코드에서 빈 `Sdf.Path()` authoring 호출은 발견하지 못했고, 두 경고와 red transient의 직접 인과는 확인되지 않았다.

현재 판정은 `RUNNER_PREPARED_HOST_EXECUTION_REQUIRED`이다. 29354는 29806 저장 영상 전체의 사람 검토 전까지 차단한다.
