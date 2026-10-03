# Issue ledger

| 시각 | 사례 | 단계 | 증상/상태 | 판정 |
|---|---|---|---|---|
| 2026-10-03 | 공통 | 준비 | 기존 사용자 untracked 파일 다수 확인 | 건드리지 않고 새 폴더만 사용 |
| 2026-10-03 | 29806 | 입력 gate | USD SHA256과 기존 Git 기록 일치 | 입력 확인 완료, GUI/physics 미실행 |
| 2026-10-03 | 29354 | 입력 gate | USD SHA256과 기존 Git 기록 일치 | 입력 확인 완료, GUI/physics 미실행 |
| 2026-10-03 | 29806 | 첫 shell gate | `STRUCTURE_GATE_PASS_PHYSICS_NOT_STARTED`라는 이름과 달리 Isaac composed stage는 열지 않음 | 범위를 입력/GPU/X11 gate로 정정. 새 runner 내부에 실제 composed mapping gate 추가 |
| 2026-10-03 | 29806 | 첫 GUI physics/capture | 사람 화면에서 길쭉한 base와 한 판만 뚜렷하며 세 문 독립 구조가 식별되지 않음. 자동 validator도 `FAIL` | `INVALID_VISUAL_MAPPING`; MP4 SHA `d6a2759f...`는 staging에만 격리, 공식 링크/GIF 금지 |
| 2026-10-03 | 29806 | mapping 기록 감사 | body 관계와 Mesh component는 분리됐으나 모든 clone이 같은 색이고 marker에 원래 ancestor 및 world bounds 비교가 없음 | 물리 없는 회색 base + 빨강/초록/파랑 door static gate로 교체 |
| 2026-10-03 | 29806 | 색상 static gate | 화면에 가느다란 수평선만 보임 | JSON에서 문들이 XY 면이고 Z가 최소 두께인데 camera가 +Y였음을 확인. up-axis Z를 view 후보에서 제외한 규칙이 원인. ±X/±Y/±Z capture gate로 교체 |
| 2026-10-03 | 29806 | 색상 static gate 종료 | stdout 완료 marker와 JSON은 존재하지만 wrapper exit code 2 | 새 gate는 rc 2를 단독 성공으로 보지 않고 완료 marker+JSON+6 PNG+contact-sheet validator가 모두 있을 때만 자동 준비 상태로 인정 |

실행 오류는 같은 명령을 반복하지 않고 `LOG_DIR`, 최초 예외, physics 시작 전/후 여부를 새 행으로 기록한다.
| 2026-10-03 | 29806 | six-view static gate | +X 화면 뒤 GUI 응답 없음, shell rc=124; staging 파일 0개, 완료 marker 없음 | 동기식 첫 ffmpeg 호출에서 event loop가 막힌 강한 코드순서 근거. GPU/mesh 실패로 단정하지 않음. Popen+app.update+camera별 15초 watchdog으로 수정 |
| 2026-10-03 | 29806 | 19:58 six-view static gate | `app ready` 후 `plus_X` CAPTURE_RUNNING에서 240초 timeout. PNG 0, contact sheet/JSON/완료 marker 없음. ffmpeg stderr는 banner만 1,858 bytes, stdout 0 bytes | Popen 수정도 해결하지 못함. external capture가 입력을 열지 못한 동안 `app.update()` 호출도 복귀하지 않은 것으로 추론. 대응 Kit log/traceback이 없어 내부 호출은 미확정. GPU/mesh/USD 실패 판정 안 함 |
| 2026-10-03 | 29806 | static gate 재설계 | 복잡한 6-view X11 자동 capture를 static runner에서 제거 | Z-thin-axis 정면 단일 GUI와 relationship/bounds JSON만 제공. physics 0 step, external capture 0건. 사람이 회색 base+빨강/초록/파랑 3문을 확인하기 전까지 physics 차단 유지 |
