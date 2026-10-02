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

static runner는 joint `body0/body1`, fixed-joint graph, 모든 source Mesh의 원래 rigid-body ancestor, target component, source/reconstructed world bounds와 round-trip 오차를 기록한다. base는 회색, `gt_C_1/2/3` 문 component는 각각 빨강/초록/파랑으로 표시한다. `PhysicsScene`, timeline, tensor와 capture는 시작하지 않으며 simulation step은 0이다. 사람 확인에서 수납장 base와 서로 다른 위치의 세 문이 동시에 보일 때만 이후 physics runner 차단을 해제한다.

## 범위 제한

- generated output이나 AI 예측 관절값을 사용하지 않는다.
- 기존 headless의 “초기화 3회”는 독립 reset 3회가 아니라 neutral target 60-step 구간 3회였다는 정정을 유지한다.
- range 밖 target 요청이나 target readback만으로 mechanical limit 정확도를 주장하지 않는다.
- 새 저장 영상을 사람이 끝까지 보기 전 `HUMAN_VIDEO_REVIEW=PASS`로 기록하지 않는다.
