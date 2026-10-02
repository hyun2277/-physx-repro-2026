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

## 새 시도 기록 규칙

각 시도는 가설 하나와 주요 변경 하나만 기록한다. GUI cube가 검으면 10163을 열지 않는다. 화면을 사람이 확인하지 않은 상태에서는 screenshot·viewport 성공을 주장하지 않는다.

