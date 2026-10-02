# 이슈 통합 기록

사람 능동 작업시간과 프로그램 대기시간은 2026-10-03 새 GUI 시도부터 기록한다. 과거 시도는 `미기록/확인 불가`다.

| 발견일 | 이슈 | 증상·근거 | 원인 확정도 | 시도·변경 | 재검증 결과 | 상태 | 사람 시간 | 대기시간 |
|---|---|---|---|---|---|---|---|---|
| 2026-10-02 | legacy ML CUDA ABI | `omni.isaac.ml_archive`의 `libc10_cuda.so`가 `cudaGetDriverEntryPointByVersion` symbol 오류 | 직접 traceback으로 확정 | ML/ROS를 제외한 custom Kit experience 사용 | importer/physics minimal smoke 통과 | 우회 해결 | 미기록 | 미기록 |
| 2026-10-02 | Physics=none variant 검사 | 기본 variant를 순회해 revolute joint 0개로 오판 | variant audit으로 확정 | `Physics=physx` composed stage 검사 | 10163 1개, 29806 3개 확인 | 해결 | 미기록 | 미기록 |
| 2026-10-02 | PhysicsScene 미등록 | `No simulation registered` | manager/scene 로그로 확정 | session layer PhysicsScene 등록 | step counter 증가 | 해결 | 미기록 | 미기록 |
| 2026-10-02 | GPU direct API와 USD Drive target 충돌 | 실행 중 PhysicsDriveAPI target authoring 금지 | PhysX 오류로 확정 | USD authoring 대신 tensor control 조사 | 아래 Warp 경로로 전환 | 해결 | 미기록 | 미기록 |
| 2026-10-02 | Warp tensor control 전환 | articulation/DOF target·state API 필요 | 설치 API와 smoke로 확인 | `omni.physics.tensors` ArticulationView 사용 | 10163·29806 state 실행 PASS | 해결 | 미기록 | 미기록 |
| 2026-10-02 | swapchain 검은 영상 | 10163 viewport MP4가 사실상 검정 | ffmpeg/frame 검사로 확정 | headless swapchain capture 중단 | `INVALID_BLACK_CAPTURE` | 미해결 | 미기록 | 미기록 |
| 2026-10-02 | Replicator RGB black | annotator 3장+BasicWriter 3장 생성; annotator 통계 모두 0 | failure JSON으로 확정 | ML/ROS 제외 render Kit r11까지 점검 | `BLOCKED_RGB_BLACK` | 미해결 | 미기록 | 미기록 |
| 2026-10-03 | Fabric/render 동기화 | 기존 step이 `update_fabric=False` | 관련 가능성은 코드로 확인, 검은 화면 원인은 미확정 | GUI 시험에서 공식 Fabric update 경로 사용 예정 | 미실행 | 가설 검증 예정 | 0 | 0 |
| 2026-10-03 | 초기화 의미 | 과거 “초기화 3회”가 독립 reset으로 읽힘 | 코드로 확정 | 60-step neutral target 세 구간으로 설명 정정 | 독립 초기화 3회는 새 실행 필요 | 설명 수정 | 미기록 | 미기록 |
| 2026-10-03 | 2,400 step 설명 | record 산식이 불명확 | 코드·Linux report phase로 확정 | 8 targets × 30 steps × 10 cycles로 기록 | 일치 | 설명 완료 | 미기록 | 미기록 |
| 2026-10-03 | 29354 drift 검사 범위 | 전체 link drift처럼 읽힐 수 있음 | 코드 배열 접근으로 확정 | 첫 link translation만 검사했다고 정정 | 전체 link translation/orientation 재측정 필요 | 미해결 | 미기록 | 미기록 |
| 2026-10-03 | session-layer 재현성 | 원본 USD와 runtime PhysicsScene/물성 설정이 분리됨 | 기존 runner로 확인 | 새 실행에서 원본 hash와 override manifest 분리 예정 | 미실행 | 진행 예정 | 0 | 0 |
| 2026-10-02 | GUI GPU Foundation device | GUI cube 재시도에서 `Failed to create any GPU devices` | 로그로 증상 확정; GPU/driver/IOMMU 단일 원인은 미확정 | `CUDA_VISIBLE_DEVICES=1` 제거, physical GPU 1 index를 명시 | 재실행 대기 | 진행 예정 | 0 | 0 |
| 2026-10-02 | GUI renderer surface/backbuffer | `Failed to find a graphics and/or presenting queue` → `createSwapchain failed` → 반복 `backbuffers are not initialized` | window surface presentation 실패는 확정; DISPLAY/Xorg/Wayland mapping 원인은 미확정 | official base의 viewport/window/capture 설정 보완, host display diagnostics 추가 | 재실행 대기 | 진행 예정 | 0 | 0 |

### GUI GPU Foundation 진단 근거

`20261002T162120Z-cube-c35b9940-3d26-44ab-98c8-70c65fc2980c`의 Kit log는 Vulkan API와 RTX 5090 두 장을 열거했다. GPU 0은 UUID prefix `ff124b39`, PCI bus `1`; GPU 1은 UUID prefix `843dced4`, PCI bus `2`였다. command에는 `CUDA_VISIBLE_DEVICES=1`, `renderer.activeGpu=0`, `physics.cudaDevice=0`가 있었다. RTX는 `CUDA_VISIBLE_DEVICES environment variable is set`, `matching CUDA device could not be found`, `activeGpu 0 is not compatible`를 순서대로 남겼으며 active device column은 비어 있었다.

설치된 공식 GUI path는 `tools/isaac-sim/isaac-sim.sh --no-ros-env`이며 `apps/isaacsim.exp.full.kit`을 연다. full experience는 base experience를 통해 `omni.isaac.ml_archive`를 의존하므로 기존 ABI 오류 경로를 다시 불러온다. 이번 custom Kit는 설치된 `omni.usd`, viewport, renderer, PhysX extension만 직접 선언하고 ML/ROS는 포함하지 않는다. GPU 1만 선택하되 renderer가 CUDA와 physical Vulkan device를 매칭할 수 있게 visibility masking은 사용하지 않는다.

### GUI renderer surface/backbuffer 진단 근거

`20261002T162753Z-cube-2abb8501-74b6-45da-b56e-16360ceaed8e`의 Kit log는 `Created window: width=1440,height=900`까지 도달했다. 이어 `Failed to find a graphics and/or presenting queue`, `GPU ... cannot present rendered content`, `createSwapchain failed`, `Failed to initialize graphics environment`가 발생했다. 이후 backbuffer 오류는 원인이 아니라 swapchain 생성 실패의 후속 증상이다. GPU 1은 `Display Attached: Yes`, `Display Active: Enabled`로 열거되고 PhysX는 device 1을 선택했다. 이 사실만으로 현재 DISPLAY/Xorg 또는 Wayland surface가 GPU 1과 호환된다고 결론 내릴 수는 없다.

새 runner는 `DISPLAY`, `WAYLAND_DISPLAY`, `XDG_SESSION_TYPE`, `XAUTHORITY`, `xrandr --listproviders`, `xrandr --query`, 가능하면 `vulkaninfo --summary`를 실행별 log에 보존한다. `createSwapchain` 또는 backbuffer 오류가 있으면 automation marker가 있어도 `FAIL_AUTOMATION_OR_RENDERER_SURFACE`로 판정한다.

## 새 시도 기록 규칙

각 시도는 가설 하나와 주요 변경 하나만 기록한다. GUI cube가 검으면 10163을 열지 않는다. 화면을 사람이 확인하지 않은 상태에서는 screenshot·viewport 성공을 주장하지 않는다.
