# 29806·29354 GT-only Isaac Sim GUI 증거

이 폴더는 **GT-only reference — not AI prediction** 검증을 위한 실행 준비 기록이다. 기존 GPU 1 headless 결과와 새 GPU 0 GUI 실행은 서로 다른 실행으로 취급한다.

## 2026-10-05 — initialization recovery 통합 runner

Initialization-only 실행은 `SimulationManager.initialize_physics()`에서 manager step이 0→2가 된 직후 red door pixel이 사라진 것을 확인했다. authored USD의 root/body/linked-clone transform은 전후 동일했고 tensor 상태는 유한한 작은 각도·속도였다. 큰 body snap이나 collision 폭발은 확인되지 않았으며 runtime/Fabric presentation, occlusion, constraint/collision correction은 후보로 남는다. 상세 수치와 네 실행 비교는 [준비 감사](29806_gated_recovery_preparation.md) 및 [JSON](29806_gated_recovery_preparation_audit.json)에 기록했다.

새 `run_gui_29806_gpu0_gated_recovery_end_to_end.sh`는 세 관절의 근거 있는 closed target 0 rad를 매 step 보내는 최대 300-step recovery를 먼저 수행한다. 20% pixel/40px 기준은 transient 관찰용일 뿐이다. recorder gate는 문 70%, base 80%, bbox IoU 0.65, 동적 center 한계, 속도 0.01 rad/s 등 모든 최종 조건을 30 step 연속 만족하고 1.5초 hold 뒤 다시 pixel gate를 통과해야 열린다. Host 실행 전 상태는 `RUNNER_PREPARED_HOST_EXECUTION_REQUIRED`이며 29354는 계속 차단한다.

## 순차 gate

1. `29806`을 먼저 실행한다. 실제 USD 관계를 따라 세 회전관절과 문 시각 mesh를 매핑하고, 세 DOF를 하나씩 구동한다.
2. 저장 MP4·수치 로그·문별 독립 움직임을 검증하기 전에는 `29354`를 실행하지 않는다.
3. `29354`는 joint target 없이 180 passive step을 수행하며 모든 link의 translation 및 quaternion 부호 동치를 고려한 orientation drift를 계산한다.

현재 상태는 `INVALID_VISUAL_MAPPING_QUARANTINED_STATIC_GATE_REQUIRED`이다. GUI physics나 영상 성공으로 기록하지 않는다. 기존 end-to-end shell은 정적 gate의 사람 확인 전 실행되지 않도록 exit 13으로 차단했다.

첫 shell gate `20261002T191945Z-...`가 확인한 것은 입력 hash, GPU 0 identity/free memory, compute process 부재, X11 접근뿐이다. 그 gate는 Isaac을 시작하지 않았으므로 composed joint/fixed-chain/mesh 대응을 확인한 것으로 확대하지 않는다. 새 runner가 Isaac composed stage에서 이 관계를 다시 계산해 `marker_structure_mapping.json`에 저장하며, mapping이 모호하거나 예상 schema 수가 다르면 physics 전에 종료한다.

## 고정 입력

| 사례 | USD | SHA256 | variant | 예상 구조 |
|---|---|---|---|---|
| 29806 | `/home/minsujo/Desktop/SH/PHYSx/staging/gt-only-isaac-control-20261002T072614Z-gt-only-control/29806/gt_29806/gt_29806.usda` | `5da6eb5823de2a8da1d7896ad047c8a73b2f25c79b60bd606afe912dd1b0891a` | `physx` | revolute 3, rigid body 11, collider 8 |
| 29354 | `/home/minsujo/Desktop/SH/PHYSx/staging/gt-only-isaac-control-20261002T072614Z-gt-only-control/29354/gt_29354/gt_29354.usda` | `577a38f19dc54854f9e657f008f591bea5edcc195fffd84b0adc47a9998576fd` | `physics` | revolute/prismatic 0, fixed 6, DOF 0 |

29806의 각 문은 joint `body0/body1` 및 fixed-joint 연결 graph로만 결정한다. 10163 이름이나 camera/mesh 매핑을 복사하지 않는다. 원본 instance mesh가 보이지 않을 때의 표시 clone은 source topology를 해당 rigid body local space로 한 번 변환해 자식으로 만들며, simulation 시작 뒤 clone xform이나 time sample을 author하지 않는다.

29354의 과거 `1.0280995564419422e-07 m`는 첫 link translation 관측값으로만 유지한다. 새 실행은 tensor 배열 shape와 link 이름을 기록하고 모든 link에 대해 `max ||t-t0||` 및 `2 acos(|dot(q,q0)|)`를 계산한다. 사전 기준은 translation `1e-3 m`, orientation `1e-3 rad`, finite state, DOF 0, target 호출 0회이다.

## 실행

29806의 physics 없는 정적 색상 mapping gate만 실행한다.

```bash
cd /home/minsujo/Desktop/SH/PHYSx/repro-records && ./04_PhysX-3D/04_한계및후속작업/2026-10-03_29806_29354_GT_only_GUI_증거/run_gui_29806_gpu0_static_mapping_gate.sh
```

static runner는 joint `body0/body1`, fixed-joint graph, 모든 source Mesh의 원래 rigid-body ancestor, target component, source와 **실제 author된 clone** world bounds 및 vertex 오차를 기록한다. base는 회색, `gt_C_1/2/3` 문 component는 각각 빨강/초록/파랑으로 표시한다. stage bounds의 최소 두께 축인 Z 정면에서 보이는 단일 GUI 화면을 30초간 유지한다. 이 gate에서 외부 X11 capture를 시작하지 않는다. `PhysicsScene`, timeline, tensor는 시작하지 않으며 simulation step은 0이다. 사람 확인에서 수납장 base와 서로 다른 위치의 세 문이 동시에 보일 때만 이후 physics runner 차단을 해제한다.

## 범위 제한

- generated output이나 AI 예측 관절값을 사용하지 않는다.
- 기존 headless의 “초기화 3회”는 독립 reset 3회가 아니라 neutral target 60-step 구간 3회였다는 정정을 유지한다.
- range 밖 target 요청이나 target readback만으로 mechanical limit 정확도를 주장하지 않는다.
- 새 저장 영상을 사람이 끝까지 보기 전 `HUMAN_VIDEO_REVIEW=PASS`로 기록하지 않는다.

### 19:58 timeout 감사

`20261002T195815Z-...` 재시도는 `app ready` 뒤 첫 `plus_X` capture를 `CAPTURE_RUNNING`으로 표시한 상태에서 240초 wrapper timeout으로 종료됐다. PNG, contact sheet, `static_mapping_gate.json`, 완료 marker는 없다. `ffmpeg_plus_X.stderr`는 1,858 bytes의 build banner만 남겨 X11 input open이나 frame output을 확인할 수 없다. 이는 GPU·mesh·USD 실패로 판정하지 않는다. 코드 순서와 파일 상태는 in-process GUI update와 external X11 capture가 같이 정지한 경로를 가리키지만, traceback과 대응 Kit log가 없어 내부 blocking call은 미확정이다. 세부 기록은 `29806_static_gate_timeout_1958_audit.json`에 분리했다.

## +Z 사람 확인 실패와 새 gate

커밋 `25a90d7...`의 실행 `20261003T105740Z-...`은 app/stage/8개 clone/direct material/camera 생성 후 30초 표시를 마치고 exit 0이었다. PhysicsScene, tensor, timeline은 사용하지 않았고 physics step은 0이다. 그러나 사람이 본 화면은 거대한 흰 면 하나였으며 회색 본체·세 색 문·주황 cube를 구분할 수 없었다. 따라서 자동 marker보다 사람 관측을 우선해 `HUMAN_CHECK_FAIL`로 기록한다.

흰 면의 정확한 prim은 pixel/object-ID 증거가 없어 미확정이다. +Z 깊이 순서에서 문 앞을 넓게 덮는 강한 후보는 source `/gt_29806/Geometry/world/l_0/l_4/tn__4_/tn__4_`와 clone `__GuiDiagnosticMesh_3`이지만 확정으로 쓰지 않는다. `29806_plusZ_human_fail_audit.json`에 근거와 한계를 기록했다.

새 gate는 원본 Mesh와 실제 author된 clone을 모두 감사하고, direct/computed material이 같은지 검사한다. ±X/±Y/±Z와 두 사선 후보의 projected door 면적, 문 중심 분리, edge-on 여부, base depth 가림 위험, clipping 여백을 수치 비교해 한 시점을 선택한다. 기존 bounds로 계산한 예상 선택은 `minus_Z`이나 실제 실행 report의 선택값을 기준으로 한다. 외부 X11 capture는 호출하지 않는다. GUI는 45초 유지하며 1초 heartbeat와 개별 `app.update()` 5초 watchdog을 기록한다.

현재 판정은 `RUNNER_PREPARED_HUMAN_CHECK_REQUIRED`이다. 사람이 수납장 형태와 회색 base, 서로 다른 위치의 빨강·초록·파랑 문, 작은 주황 cube를 확인하기 전까지 physics shell의 exit 13 차단을 유지한다.

## 11:31 내부 viewport pixel gate

이전 `20261003T111210Z-...` 실행은 수치 gate와 정상 종료까지 통과했지만, 사람 화면에서 진단 geometry가 하나도 보이지 않아 `HUMAN_CHECK_FAIL_NO_RENDERED_DIAGNOSTIC_GEOMETRY`이다. 활성 camera는 `/__PhysXGuiDiagnostic/Camera_front`이고 후보 label은 `minus_Z`로 같은 camera를 가리킨다.

수정 runner는 설치된 Kit 110의 `omni.kit.viewport.utility.capture_viewport_to_file`과 `next_viewport_frame_async`를 사용해 **활성 Viewport/Viewport0**의 단일 프레임을 내부 캡처한다. 외부 X11/ffmpeg capture는 사용하지 않는다. world-space 일반 Mesh clone 8개에 extent, default purpose, inherited visibility, double-sided, direct PreviewSurface와 emissive 색상을 명시했다. 같은 session layer/frustum에 주황 reference cube, magenta cube, cyan thin cube를 두었다. viewport axis/grid/selection guide는 USD joint를 바꾸지 않고 Kit per-viewport setting으로 숨겼다.

실행 `20261003T113111Z-...`은 1280×720 PNG(70,419 bytes, SHA256 `867aefac19ee66c1e0034518c6996fd82b1f66962ac93618fa83c00697aaf1fd`)를 만들었다. 최대 4-connected component 기준 pixel 수는 base 4,587, C1 red 48,975, C2 green 60,248, C3 blue 60,272, reference orange 1,695, control magenta 855, control cyan 236이다. 문 중심 최소 거리는 223.057 px이며 모두 별도 bbox이다. non-black 비율은 0.193507이다. source↔실제 author clone 최대 vertex 오차는 `4.928568641186635e-11 m`이다.

자동 상태는 `AUTOMATION_RENDER_PIXEL_GATE_PASS_HUMAN_CHECK_REQUIRED`이다. PhysicsScene, tensor, timeline을 시작하지 않았고 physics step은 0이다. 이 실행의 저장 PNG에서는 회색 수납장 frame, 서로 다른 빨강·초록·파랑 문, 주황 reference cube, 두 control이 확인되지만, 실제 GUI 사람 확인은 아직 별도 `PENDING`이다. 이전 검은 화면의 단일 확정 원인은 분리하지 못했다. 새 경로는 world-space clone, 명시적 렌더 속성, emissive direct material, render warmup/internal capture를 함께 바꿨기 때문이다.

## 정적 gate 사람 확인 완료와 물리 runner 준비

사용자는 `20261003T113111Z-...` GPU 0 GUI에서 회색 수납장 base, 서로 다른 위치의 넓은 빨강·초록·파랑 문, 별도 위치의 reference/control geometry를 직접 확인했다. 거대한 흰 면, 선만 보이는 자산, 본체 아래의 노트북형 판은 없었다. 따라서 정적 범위의 판정은 `STATIC_MAPPING_AUTOMATION_AND_HUMAN_PASS`이다. 이 확인은 physics step 0인 body↔door **정적 시각 매핑**에만 적용하며 물리 구동 또는 영상 성공을 뜻하지 않는다.

물리 runner는 같은 GT USD와 relationship-derived mapping으로 body-local linked clone을 만들고, physics 초기화 전에 3/4 camera의 내부 viewport PNG에서 base와 세 문을 다시 검출한다. 실제 GT limits의 8%를 닫힘, 42%를 보수적 열린 목표로 사용한다. 사전 고정 임계값은 active span ≥0.50 rad, closed-target absolute error ≤0.01 rad, inactive excursion ≤0.002 rad, root translation ≤0.0001 m, root orientation ≤0.002 rad이다. `update_fabric=True`와 Warp tensor target만 사용하며 실행 시작 뒤 clone xform/timeSample을 author하지 않는다. 실제 호스트 실행 전 상태는 `RUNNER_PREPARED_HOST_EXECUTION_REQUIRED`이다.

## 첫 GUI physics 실행 실패와 수정된 시간축

실행 `20261003T120142Z-...`은 `INVALID_FAST_VISUAL_AND_INACTIVE_DOF_DRIFT`이다. pre-physics linked-clone PNG는 PASS했지만 Physics/Fabric 초기화 뒤의 pixel 표본과 영상은 생성되지 않았다. 450개 pretest record는 manager step 3→453, record wall time 9.079초였고, 이후 inactive drift 검사에서 중단됐다. `physics_records.jsonl`, MP4, ffmpeg 로그, 대표 프레임, video validation, 성공 marker는 생성되지 않았다. 따라서 사람이 본 시작 시 문 사라짐의 정확한 step·wall time은 이 실행 자료만으로 확정할 수 없다.

기존 drift 식은 검증된 settle baseline 없이 비구동 joint 위치를 명목 closed target과 비교했고, 이전 관절의 복귀/settling 영향을 섞었다. 보완 runner는 두 지표를 분리한다. `closed_target_absolute_error_rad`는 다음 문 구동 전에 문별 measured position과 closed target의 절대오차를 검사하며 기준은 `≤0.01 rad`이다. 이를 통과한 실측값만 baseline으로 삼고, 다른 문이 실제 opening/open-hold/closing 구간일 때만 `inactive_excursion_from_settled_baseline_rad`를 계산하며 기준은 `≤0.002 rad`이다. 자기 active 및 자기 settle 구간은 제외한다. 매 physics step에는 세 DOF target vector 전체를 다시 보낸다.

문별 고정 wall-clock 구간은 닫힘 1.5초, 열기 smoothstep 3초, 열린 hold 1.5초, 닫기 smoothstep 3초다. 이후 settle은 절대오차 `≤0.01 rad`와 속도 `≤0.05 rad/s`를 30 step 연속 만족해야 끝나며 최대 300 step(5초)에서 timeout된다. 따라서 시작/끝 정적 구간을 포함한 예상 영상 범위는 약 `31.5–45.0초`이고 결과 summary에는 실제 문별 settle step·시간·measured position·절대오차·baseline·최대 속도와 비구동 excursion 원값을 남긴다. root 기준은 translation `≤1e-4 m`, orientation `≤0.002 rad`인 보수적 GUI smoke 운영 기준이며, 이전 headless 결과와 동등 정확도를 뜻하지 않는다. 초기 linked clone pixel gate 뒤 Physics 초기화 transient는 보존한다. 20%/40px 기준은 관찰 상태로만 기록하며, recovery의 엄격 수치·시각 조건을 30 step 연속 만족하고 1.5초 hold 후 재검사하기 전에는 recorder와 active 구동을 시작하지 않는다.

현재 상태는 `RUNNER_PREPARED_HOST_EXECUTION_REQUIRED`이다. 29354는 계속 미실행이다.

## 2026-10-04 초기화 직후 시각 연속성 차단

실행 `20261004T160703Z-...`은 `VISUAL_CONTINUITY_GATE_FAIL_AFTER_INITIALIZE_GT_C_1_MISSING`이다. pre-physics PNG에서 빨간 문은 48,954 px와 bbox `[302,233,507,486]`였으나 `SimulationManager.initialize_physics()` 뒤 manager step 2에서 red mask가 0이 됐다. 같은 영역의 nonblack 비율은 `0.98765→0.04531`로 감소했고 red-like pixel도 `49,122→0`이었다. 초록 문은 18.728 px 이동하고 74.28% 면적으로 남았으며 파랑과 base는 거의 유지됐다. active target schedule, recorder, physics records는 시작되지 않았다.

실패 실행에는 초기화 전후 body/clone transform, tensor joint position·velocity, depth/object ID가 없어 RGB만으로 body snap, occlusion, linked-clone/Fabric sync 중 하나를 확정할 수 없다. 별도 initialization-only 모드는 동일 linked clone·camera·material을 유지한 채 target 명령과 recorder 없이 초기화 및 최대 step 10까지만 검사한다. 각 단계에서 USD transform/bounds/material, tensor position/velocity/link pose, 내부 viewport PNG를 남기고 문이 사라진 첫 단계에서 중단한다. 설치 소스에서 확인된 depth API는 `isaacsim.test.utils.image_capture.capture_depth_data_async`지만 Replicator render product를 추가하는 경로이므로 이 최소 진단에는 섞지 않는다. 일반 viewport prim-ID API는 설치 예제에서 확인되지 않아 지원 여부를 추정하지 않는다. 초기 joint state는 아직 수정하지 않는다.

정적 payload 대조에서 세 `abstract_*` body의 authored translation은 각 joint의 `localPos0`와 일치하고 `localPos1=(0,0,0)`, 양쪽 `localRot=identity`, axis=Y이다. 따라서 serialized authored geometry가 나타내는 joint coordinate는 세 joint 모두 `0 rad`이며 limit `[-π,0]` 안이다. `physics.usda`에는 명시적 drive target 값이 없고 실패 실행에는 tensor 초기 position이 남지 않았으므로, 이 정적 결과만으로 runtime mismatch나 snap 원인을 확정하지 않는다. 근거가 확보되기 전에는 초기 joint state를 설정하거나 수정하지 않는다.
