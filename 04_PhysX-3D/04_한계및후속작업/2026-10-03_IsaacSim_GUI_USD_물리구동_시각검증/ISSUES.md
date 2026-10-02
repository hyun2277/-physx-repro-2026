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
| 2026-10-02 | GUI renderer surface/backbuffer | `Failed to find a graphics and/or presenting queue` → `createSwapchain failed` → 반복 `backbuffers are not initialized` | GPU 1 Vulkan/RTX 선택과 GPU Foundation은 성공했으나 현재 X11 surface에 present queue를 만들지 못함. 물리 모니터는 GPU 1, X source provider는 GPU 0인 PRIME topology 확인. GPU별 queue-family present bit는 도구 부재로 미확정 | official base의 viewport/window/capture 설정을 보완했으나 동일 실패. 추가 설정 변경 없이 topology 감사로 전환 | 세 번째 cube도 재실패; 10163 미실행 | GPU 1 GUI 미해결 | 사용자 실행·관찰 시간 미기록 | 약 70초 후 Ctrl+C |

### GUI GPU Foundation 진단 근거

`20261002T162120Z-cube-c35b9940-3d26-44ab-98c8-70c65fc2980c`의 Kit log는 Vulkan API와 RTX 5090 두 장을 열거했다. GPU 0은 UUID prefix `ff124b39`, PCI bus `1`; GPU 1은 UUID prefix `843dced4`, PCI bus `2`였다. command에는 `CUDA_VISIBLE_DEVICES=1`, `renderer.activeGpu=0`, `physics.cudaDevice=0`가 있었다. RTX는 `CUDA_VISIBLE_DEVICES environment variable is set`, `matching CUDA device could not be found`, `activeGpu 0 is not compatible`를 순서대로 남겼으며 active device column은 비어 있었다.

설치된 공식 GUI path는 `tools/isaac-sim/isaac-sim.sh --no-ros-env`이며 `apps/isaacsim.exp.full.kit`을 연다. full experience는 base experience를 통해 `omni.isaac.ml_archive`를 의존하므로 기존 ABI 오류 경로를 다시 불러온다. 이번 custom Kit는 설치된 `omni.usd`, viewport, renderer, PhysX extension만 직접 선언하고 ML/ROS는 포함하지 않는다. GPU 1만 선택하되 renderer가 CUDA와 physical Vulkan device를 매칭할 수 있게 visibility masking은 사용하지 않는다.

### GUI renderer surface/backbuffer 진단 근거

`20261002T162753Z-cube-2abb8501-74b6-45da-b56e-16360ceaed8e`의 Kit log는 `Created window: width=1440,height=900`까지 도달했다. 이어 `Failed to find a graphics and/or presenting queue`, `GPU ... cannot present rendered content`, `createSwapchain failed`, `Failed to initialize graphics environment`가 발생했다. 이후 backbuffer 오류는 원인이 아니라 swapchain 생성 실패의 후속 증상이다. GPU 1은 `Display Attached: Yes`, `Display Active: Enabled`로 열거되고 PhysX는 device 1을 선택했다. 이 사실만으로 현재 DISPLAY/Xorg 또는 Wayland surface가 GPU 1과 호환된다고 결론 내릴 수는 없다.

새 runner는 `DISPLAY`, `WAYLAND_DISPLAY`, `XDG_SESSION_TYPE`, `XAUTHORITY`, `xrandr --listproviders`, `xrandr --query`, 가능하면 `vulkaninfo --summary`를 실행별 log에 보존한다. `createSwapchain` 또는 backbuffer 오류가 있으면 automation marker가 있어도 `FAIL_AUTOMATION_OR_RENDERER_SURFACE`로 판정한다.

### 세 번째 cube와 display topology 감사

`20261002T163957Z-cube-c57d2e3b-7949-40a0-b3a7-7f8aa7310799`에서도 같은 presentation chain이 실패했다. 이번에는 GPU 1(`GPU-843dced4-ee97-dbb8-36c9-343fe13b7647`, PCI `02:00.0`)이 Vulkan/RTX active이고 PhysX CUDA device 1인 점이 Kit log로 확인됐다. 따라서 이전 CUDA visibility mask에 따른 GPU Foundation 실패와 구분한다.

Host 기록은 X11 `DISPLAY=:0`을 사용했다. `xrandr --listproviders`에서 `NVIDIA-0`은 source, `NVIDIA-G0`은 sink였고 실제 output은 `HDMI-1-0 connected primary`였다. `nvidia-smi -q`는 GPU 1을 `Display Attached: Yes`, `Display Active: Enabled`, GPU 0을 `No/Disabled`로 기록했다. 물리 모니터 출력은 GPU 1이 소유하지만 X root/source provider는 GPU 0 계열인 PRIME/offload 구조다. Kit는 GPU 1에서 graphics device를 만들었으나 이 X surface에 대한 presenting queue를 얻지 못했다.

`vulkaninfo`와 `glxinfo`가 host에 없어 각 GPU의 queue-family `presentSupport`와 OpenGL UUID는 직접 확인하지 못했다. 두 GPU 모두 Kit가 Vulkan RTX 장치로 열거했으므로 graphics-capable인 점은 확인됐지만, GPU 1은 현재 X surface에서 present 실패, GPU 0은 이번 실행에서 inactive라 present 상태가 미검증이다. 최신 읽기 전용 조회에서 GPU 0 메모리는 376/32,607 MiB, GPU 1은 66/32,607 MiB였고 compute process는 없었다.

공식 `isaac-sim.sh --no-ros-env`는 `apps/isaacsim.exp.full.kit`을 열지만 이 설치에서는 base dependency의 `omni.isaac.ml_archive`가 기존 CUDA ABI 오류를 일으킨다. custom Kit는 ML/ROS를 제외하고 공식 base의 window/viewport/renderer 구성을 반영했는데도 동일 present 실패가 발생했으므로, extension 누락만을 현재 원인으로 보지 않는다.

다음 최소 진단 후보는 X source provider인 physical GPU 0에서 **physics 없이 GUI cube presentation만** 한 번 검사하는 것이다. 이는 기존 GPU 1 전용 정책을 바꾸므로 사용자 확인 전 실행하지 않는다. GPU 0 GUI+physics, multi-GPU/P2P, Xorg·driver·IOMMU 변경은 제안하지 않는다. livestream/offscreen은 공식 대체 경로 후보지만 기존 Replicator black과 별개의 사전검증이 필요해 차순위다.

2026-10-03 사용자가 이 GPU 0 cube-only 검사 1회를 승인했다. 별도 experience에서 physics extension과 physics device 설정을 제거하고 renderer active GPU 0만 지정했다. 실행 직전 UUID `GPU-ff124b39-8b48-7d2a-bf74-bf6a5c8f1716`, PCI `01:00.0`, memory 및 compute process를 재검사한다. 자동 marker와 renderer 오류 부재는 화면 가시성의 필요조건일 뿐이며, 조명된 cube·viewport·Stage tree를 사람이 확인하고 screenshot을 남기기 전에는 `GUI_VISIBLE=PASS`로 판정하지 않는다.

### GPU 0 cube GUI 사람 확인

`20261002T165125Z-cube-gpu0-6e7dd0e5-1047-45e2-ab41-2d2b174bc3f2`는 exit code 0, 모든 자동 marker, window 생성, swapchain/backbuffer 오류 0을 기록했다. 사용자가 viewport의 렌더링된 cube, Stage tree의 `World/VisibleCube`, Property panel의 `/World/VisibleCube`, `KeyLight`와 `DistantLight`를 직접 확인했으므로 이 실행은 `GUI_VISIBLE=PASS`다. screenshot 원본은 Windows 로컬 `C:\Users\sh050\Desktop\physX\1003\아이작심1.PNG`에만 있으며 Linux 또는 Git에 있다고 주장하지 않는다.

해결 범위는 GPU 0에서 기본 Isaac GUI·USD stage presentation이 가능하다는 점이다. GPU 1의 X surface present 실패 원인은 그대로 남아 있고, 10163·29806·29354 USD loading과 physics는 이번 실행에서 다루지 않았다.

### 10163 GPU 0 static USD inspection 준비

사용자는 GPU 0 GUI에 기존 10163 GT-only USD를 정적으로 여는 검사 1회를 승인했다. 별도 experience와 runner는 `Physics=physx` payload를 compose해 schema를 읽지만 PhysX·SimulationManager·tensor extension을 의존하지 않으며 timeline을 재생하지 않는다. 자동 검사는 입력 SHA256, joint `gt_C_1`, articulation root, rigid body, collider와 zero-step guard를 확인한다. 화면에서 노트북 형상과 joint Property를 사람이 확인하기 전에는 PASS로 판정하지 않는다. 29806·29354, AI output, physics simulation은 승인 범위 밖이다.

첫 실행에서 GUI, joint Stage tree/Property는 보였지만 mesh는 보이지 않았다. composition은 geometry reference와 collider proxy까지 resolve됐고 asset-resolution 오류가 없었다. root `extentsHint`의 정상 bounds 사이에 ±`3.4028235e38` sentinel이 있으며 setup이 root를 frame한 것이 확인돼 framing이 가장 강한 원인 후보다. 다음 mesh-prim framing에서 형상이 실제로 보이기 전에는 인과를 최종 확정하지 않는다. 원본 USD·transform·lighting을 수정하지 않고 mesh prim별 extent/visibility/material/layer를 감사한 뒤 실제 mesh prim만 frame하도록 runner를 보완했다. 다음 화면에서 mesh와 `gt_C_1`가 함께 보이기 전에는 해결로 기록하지 않는다.

## 새 시도 기록 규칙

각 시도는 가설 하나와 주요 변경 하나만 기록한다. GUI cube가 검으면 10163을 열지 않는다. 화면을 사람이 확인하지 않은 상태에서는 screenshot·viewport 성공을 주장하지 않는다.
