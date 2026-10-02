# 29806·29354 GT-only Isaac Sim GUI 증거

이 폴더는 **GT-only reference — not AI prediction** 검증을 위한 실행 준비 기록이다. 기존 GPU 1 headless 결과와 새 GPU 0 GUI 실행은 서로 다른 실행으로 취급한다.

## 순차 gate

1. `29806`을 먼저 실행한다. 실제 USD 관계를 따라 세 회전관절과 문 시각 mesh를 매핑하고, 세 DOF를 하나씩 구동한다.
2. 저장 MP4·수치 로그·문별 독립 움직임을 검증하기 전에는 `29354`를 실행하지 않는다.
3. `29354`는 joint target 없이 180 passive step을 수행하며 모든 link의 translation 및 quaternion 부호 동치를 고려한 orientation drift를 계산한다.

현재 상태는 `RUNNER_PREPARED_HOST_EXECUTION_REQUIRED`이다. GUI나 physics 성공은 아직 기록하지 않는다.

## 고정 입력

| 사례 | USD | SHA256 | variant | 예상 구조 |
|---|---|---|---|---|
| 29806 | `/home/minsujo/Desktop/SH/PHYSx/staging/gt-only-isaac-control-20261002T072614Z-gt-only-control/29806/gt_29806/gt_29806.usda` | `5da6eb5823de2a8da1d7896ad047c8a73b2f25c79b60bd606afe912dd1b0891a` | `physx` | revolute 3, rigid body 11, collider 8 |
| 29354 | `/home/minsujo/Desktop/SH/PHYSx/staging/gt-only-isaac-control-20261002T072614Z-gt-only-control/29354/gt_29354/gt_29354.usda` | `577a38f19dc54854f9e657f008f591bea5edcc195fffd84b0adc47a9998576fd` | `physics` | revolute/prismatic 0, fixed 6, DOF 0 |

29806의 각 문은 joint `body0/body1` 및 fixed-joint 연결 graph로만 결정한다. 10163 이름이나 camera/mesh 매핑을 복사하지 않는다. 원본 instance mesh가 보이지 않을 때의 표시 clone은 source topology를 해당 rigid body local space로 한 번 변환해 자식으로 만들며, simulation 시작 뒤 clone xform이나 time sample을 author하지 않는다.

29354의 과거 `1.0280995564419422e-07 m`는 첫 link translation 관측값으로만 유지한다. 새 실행은 tensor 배열 shape와 link 이름을 기록하고 모든 link에 대해 `max ||t-t0||` 및 `2 acos(|dot(q,q0)|)`를 계산한다. 사전 기준은 translation `1e-3 m`, orientation `1e-3 rad`, finite state, DOF 0, target 호출 0회이다.

## 실행

29806만 먼저 실행한다.

```bash
cd /home/minsujo/Desktop/SH/PHYSx/repro-records && ./04_PhysX-3D/04_한계및후속작업/2026-10-03_29806_29354_GT_only_GUI_증거/run_29806_gpu0_gui_gate.sh
```

이 gate는 GPU 0 identity/process, X11, 입력 hash를 확인하고 기존 검증된 GPU 1 headless 실행의 원본 보고서와 이번 GUI 실행을 분리한다. 현재 버전은 구조·매핑 감사까지만 수행하며 physics/capture 실행기는 그 감사 산출물 검토 후 생성한다.

## 범위 제한

- generated output이나 AI 예측 관절값을 사용하지 않는다.
- 기존 headless의 “초기화 3회”는 독립 reset 3회가 아니라 neutral target 60-step 구간 3회였다는 정정을 유지한다.
- range 밖 target 요청이나 target readback만으로 mechanical limit 정확도를 주장하지 않는다.
- 새 저장 영상을 사람이 끝까지 보기 전 `HUMAN_VIDEO_REVIEW=PASS`로 기록하지 않는다.

