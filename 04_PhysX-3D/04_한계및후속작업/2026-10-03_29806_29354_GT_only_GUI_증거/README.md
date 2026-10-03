# 29806·29354 GT-only Isaac Sim GUI 증거

이 폴더는 **GT-only reference — not AI prediction** 검증을 위한 실행 준비 기록이다. 기존 GPU 1 headless 결과와 새 GPU 0 GUI 실행은 서로 다른 실행으로 취급한다.

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
