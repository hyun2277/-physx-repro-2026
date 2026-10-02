# 10163 GT-only GUI 물리 영상 이슈 원장

| 이슈 | 증거 | 단계 | 상태 |
|---|---|---|---|
| GPU 1 Vulkan/CUDA presentation 불일치 | 기존 GPU 1 GUI 진단 로그 | physics 전 | GPU 0 presentation으로 분리 |
| GPU 1 present queue/swapchain 실패 | `advanceCurrentFrame: backbuffers are not initialized` | physics 전 | GPU 1 GUI 경로 중단 |
| headless 검정 영상 | 기존 viewport MP4 | capture | `INVALID_BLACK_CAPTURE` |
| Replicator 검정 RGB | annotator 3장+BasicWriter 3장 | capture | `BLOCKED_RGB_BLACK` |
| root extentsHint 가설 | 실제 Mesh를 frame해도 표면 미표시 | presentation | 원인으로 철회 |
| instance-proxy material binding | 실제 Mesh binding 미입증 | physics 전 | 무효 진단 |
| static CloneMesh | GPU 0에서 cube와 노트북 형상 사람 확인 | physics 전 | 렌더 가능성 확인 |
| session de-instancing | `source Mesh did not compose ...` | physics 전 | 폐기·재시도 금지 |
| linked-clone invariant | `20261002T180919Z-10163-gpu0-static-.../stderr.log` | physics 전 | 세부 invariant 미기록 결함 보완 |
| 최종 경로 | A: `run_asset_transformer=False`; 불통과 때만 B: relationship linked clone | 실행 전 | 호스트 실행 대기 |
| 최초 통합 runner GUI 응답 저하 | `20261002T182943Z-10163-gpu0-e2e-...`; completion report/MP4 부재 | 부분 pretest 뒤 강제 종료 | sync loop 폐기, `next_update_async` 상태 머신+5초 watchdog으로 개정 |

GT-only 변환기·시뮬레이터 대조군 기록이며 PhysX-3D 자동 예측 성공 기록이 아니다.
