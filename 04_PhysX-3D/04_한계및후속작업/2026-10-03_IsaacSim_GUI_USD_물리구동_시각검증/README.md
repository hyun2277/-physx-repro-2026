# Isaac Sim GUI USD 물리 구동 시각 검증

기준 Git main: `e6b56f113d1a7199afeeb2928e8aca0f436d83b8`

작성 시작일: 2026-10-03

범위: PhysXNet GT-only 변환기·Isaac Sim 대조군. AI 자동 예측 성공 검증이 아니다.

## 교수님 질문과 현재 답

| 질문 | 현재 답 |
|---|---|
| 실제 Isaac Sim을 사용했는가? | 그렇다. Isaac Sim 6.1.0-rc의 `SimulationApp`, PhysX scene, GPU 1 Warp `omni.physics.tensors`를 사용한 headless 실행이다. |
| USD가 올바르게 로딩됐는가? | 코드상 composed `Physics=physx` stage와 schema/prim 수는 검증했다. 사람이 GUI에서 형상·Stage tree를 확인한 증거는 아직 없다. |
| 실제 physics state가 변했는가? | 10163과 29806의 measured joint position/velocity 및 PhysX step 증가는 기록됐다. 화면상의 3D 움직임과의 대응은 아직 미검증이다. |
| 기존 MP4가 3D 구동 영상인가? | 아니다. state-trace MP4는 tensor joint-state 로그의 그래프다. 기존 viewport MP4는 `INVALID_BLACK_CAPTURE`다. |
| Replicator로 정상 RGB가 생성됐는가? | 아니다. annotator 3장과 BasicWriter 3장, 총 6장이 생성됐으나 annotator 3장의 기록된 RGB 통계가 모두 0이고 최종 판정은 `BLOCKED_RGB_BLACK`이다. |
| 반복·초기화·고정 대조 검증이 충분한가? | 2,400 in-range record의 산식은 확인됐다. 그러나 과거 “초기화 3회”는 독립 reset이 아니며, 29354 drift는 전체 link 검사가 아니어서 보완이 필요하다. |

## 기존 headless 실행 흐름

1. GT-only URDF에서 변환된 USD를 `SimulationApp`으로 연다.
2. `Physics=physx` variant를 선택한다.
3. session layer에 PhysicsScene과 통제된 물성 설정을 적용한다.
4. GPU 1의 Warp `omni.physics.tensors` ArticulationView로 target을 요청하고 PhysX를 step한다.
5. joint target readback, measured position/velocity, rigid-body state를 Linux report에 기록한다.

이 흐름은 실제 Isaac Sim/PhysX 계산이지만 사람이 Isaac GUI viewport에서 USD 형상과 움직임을 확인한 절차는 아니다.

## 기존 기록 감사

### 초기화 의미

10163과 29806의 기존 코드는 단일 stage·단일 physics 초기화 안에서 neutral target `0.0`을 60 step씩 세 구간 유지했다. 이는 독립 stage reset 3회 또는 독립 프로세스 실행 3회가 아니다. 새 전체 시험에서는 독립 초기화 또는 독립 실행을 세 번 수행해야 한다.

### 2,400 in-range record

한 cycle은 정방향 목표 5개와 역방향 내부 목표 3개, 총 8개 목표 구간이다. 각 목표는 30 step이고 10 cycle이므로 `8 × 30 × 10 = 2,400` record다. Linux 원본 report의 phase/target 순서도 `-1.2, -0.6, 0, 0.6, 1.2, 0.6, 0, -0.6` 순환과 일치한다.

### 29354 drift 범위

기존 코드는 `get_link_transforms()` 결과에서 articulation별 `x[0]`만 비교했다. 따라서 기록된 `1.0280995564419422e-07 m`는 첫 link translation drift이며 전체 link drift가 아니다. orientation drift도 계산하지 않았다. 새 실행에서 모든 link의 translation과 orientation을 별도로 계산해야 한다.

### target과 limit 판정

`set_dof_position_targets()` 뒤의 target readback은 요청값 전달 확인이다. measured joint position/velocity는 실제 응답 확인이다. range 밖 target을 요청했다는 사실과 `limit + 0.05` 안에 남았다는 기존 검사만으로 양쪽 mechanical limit의 추종·접촉·안정화를 모두 검증했다고 볼 수 없다.

### Fabric/render 동기화

설치된 Isaac Sim 6.1.0-rc `SimulationManager.step(render, update_fabric)` 구현은 `update_fabric=True`일 때 최신 physics 결과를 Fabric에 반영한다고 설명한다. 기존 물리 runner는 `update_fabric=False`였다. 이는 렌더 자세 동기화에 영향을 줄 수 있으나 검은 capture의 확정 원인으로 판정하지 않는다. GUI 시험은 공식 Fabric update 경로를 사용하고 차이를 기록한다.

## 이번 검증 순서

1. GUI 기본 cube, light, viewport, Stage tree를 사람이 직접 확인한다.
2. 10163 원본 USD 경로·SHA256을 확인하고 GUI에서 `Physics=physx` variant를 연다.
3. base/lid, Stage tree, joint property, collider/physics 구조를 화면과 코드로 함께 확인한다.
4. 작은 열기·닫기 1회를 tensor target과 실제 physics step으로 수행하고 화면 움직임과 measured joint state를 대조한다.
5. 통과 후에만 5 targets, 10 round trips, 독립 초기화 3회, 양쪽 limit 시험을 수행한다.
6. 이후 29806과 29354를 같은 기준으로 검증한다.

## 성공·실패 기준

정상 3D 검증 성공은 다음이 모두 필요하다.

- 물체 형상이 GUI viewport에서 보인다.
- 화면에 표시된 stage가 기록한 USD 절대 경로와 SHA256에 연결된다.
- link/joint/schema 구조가 기대와 일치한다.
- PhysX step counter와 measured joint state가 변한다.
- 화면 움직임이 measured state와 대응한다.
- 비구동 부품이 안정적이고 관통·분리·잘못된 축 회전이 관찰되지 않는다.
- 사람이 전체 영상을 재생하고 시작·중간·끝 프레임을 확인한다.

검은 화면, 그래프 영상, target readback만으로는 성공 처리하지 않는다.

## GPU와 GUI 확인 정책

일반 Linux host의 물리 GPU 1만 사용한다. `CUDA_VISIBLE_DEVICES=1`로 한 장만 노출한 뒤 Kit 내부 renderer/physics index는 `0`으로 지정한다. CUDA logical index와 Vulkan physical GPU가 같다고 추정하지 않고, 실행 전 `nvidia-smi`의 GPU 1 UUID/PCI bus ID와 Kit 로그의 renderer 장치를 대조한다. P2P와 multi-GPU는 사용하지 않는다. IOMMU 경고는 기록만 하고 BIOS·커널 설정을 변경하지 않는다.

## 시간 기록

이번 시도부터 다음을 분리한다.

- 사람 능동 작업시간: GUI 확인, Stage tree·속성 대조, 영상 육안 검사에 실제로 쓴 시간.
- 프로그램 대기시간: Kit 시작, shader 준비, physics 실행, 저장·인코딩 대기시간.

과거 실행에는 이 구분 기록이 없어 소급 추정하지 않는다.

## 현재 상태

- 2026-10-02 GUI cube 최초 시도: **dependency solver 실패**. custom Kit에 설치된 extension을 찾을 `settings.app.exts.folders`가 없었다. `isaacsim.core.simulation_manager`를 registry에서 받지 못한 것이 아니라, 설치된 local extension `1.17.1`의 탐색 경로가 누락된 것이다. solver 종료 뒤 setup script가 실행되어 `omni.usd` import가 실패했으므로 후자는 2차 오류다. cube·USD·physics·GPU·renderer 결과는 미실행이다.
- 2026-10-02 cube 재시도: **GPU Foundation device 생성 실패**. Kit는 Vulkan으로 RTX 5090 두 장을 열거했지만 모두 CUDA match 없음으로 건너뛰었다. 명령의 `CUDA_VISIBLE_DEVICES=1`은 CUDA를 한 장만 보이게 하고, Vulkan은 physical GPU 0·1을 열거했다. 따라서 renderer 설정의 `activeGpu=0`은 Foundation settings와 호환되지 않았다. 이 기록은 GPU 1·driver·IOMMU의 개별 장애를 확정하지 않는다. cube·USD·physics는 시작되지 않았다.
- 최소 수정: `CUDA_VISIBLE_DEVICES`/`NVIDIA_VISIBLE_DEVICES`를 runner에서 해제하고, multi-GPU는 계속 끈 채 Kit의 physical `renderer.activeGpu=1`, `physics.cudaDevice=1`로 GPU 1(PCI `00000000:02:00.0`, UUID `GPU-843dced4-ee97-dbb8-36c9-343fe13b7647`)만 선택한다. 다음 실행에서 Kit log의 UUID/PCI와 실행 전 inventory를 다시 대조한다.
- 2026-10-02 cube 두 번째 재시도: **renderer surface/backbuffer 실패**. GPU Foundation 단계와 `omni.usd`/cube marker는 통과했지만, `Created window` 뒤 `Failed to find a graphics and/or presenting queue`와 `createSwapchain failed`가 발생했고, 이어서 `backbuffers are not initialized`가 반복됐다. GPU 1은 display-attached/active로 열거되었고 PhysX는 CUDA device 1을 선택했다. 그러나 현재 GUI window surface에 GPU 1이 present할 queue를 찾지 못했다. 이는 기존 Vulkan–CUDA matching 실패와 별개이며, DISPLAY/Xorg·Wayland session과 GPU 1의 presentation mapping이 아직 미확정이다. 정상 cube viewport는 나타나지 않았으므로 cube·USD·physics 성공으로 처리하지 않는다.
- 다음 최소 수정: official base Kit의 `omni.kit.viewport.window`, `omni.kit.renderer.capture`, viewport/window/app renderer settings를 custom Kit에 보완했다. GPU 1 physical index, multi-GPU off, P2P off 정책은 유지한다. runner는 DISPLAY/Wayland/Xorg provider·Vulkan summary를 기록하고, Kit log에 presenting queue/swapchain/backbuffer 오류가 있으면 exit 0이나 setup marker와 무관하게 실패 처리한다.
- GUI 기본 cube 재시도: **사용자 화면 확인 대기**
- 10163 GUI USD loading: **미실행 — cube 통과 전 실행 금지**
- 10163 스크린샷: 아직 없음
- 29806·29354: 아직 실행하지 않음

일반 Linux 실행 명령은 `run_gui_visual_validation.sh cube`이며, cube 확인 뒤 별도 지시 없이 10163 단계로 넘어가지 않는다.
