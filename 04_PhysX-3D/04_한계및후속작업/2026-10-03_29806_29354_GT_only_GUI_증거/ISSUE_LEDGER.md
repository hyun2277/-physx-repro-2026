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
| 2026-10-03 | 29806 | 단일 +Z static gate | 자동 실행은 exit 0, clone 8개와 binding 기록, 30초 표시, physics 0 step. 사람 화면은 거대한 흰 면 하나로 본체/3문/cube 식별 불가 | `HUMAN_CHECK_FAIL`. +Z 앞쪽 broad base mesh가 가림의 강한 수치 후보이나 pixel/object-ID 근거가 없어 정확한 흰 면 prim은 미확정 |
| 2026-10-03 | 29806 | static gate v2 준비 | source/clone/material/joint 감사 확장, 8개 카메라 projection/depth scoring, 외부 capture 제거, 45초 GUI heartbeat/watchdog | 기존 report로 offline 계산 시 minus_Z만 base occlusion risk 0, 세 문 edge-on 0. 실제 실행과 사람 확인 전에는 PASS 아님 |
| 2026-10-03 | 29806 | 이전 numeric static gate | `20261003T111210Z-...`은 app/stage/8 clone/material/camera/45초/정상 shutdown 통과, physics 0. 사람 화면에는 관절 guide만 보이고 asset/control/reference가 안 보임 | `STATIC_NUMERIC_GATE_PASS`와 `HUMAN_CHECK_FAIL_NO_RENDERED_DIAGNOSTIC_GEOMETRY`를 병기. camera 이름 `Camera_front`와 candidate `minus_Z`는 동일 prim이므로 이름 문제 아님 |
| 2026-10-03 | 29806 | internal viewport pixel gate | Kit 110 공식 viewport async capture로 `Viewport/Viewport0`와 active camera를 직접 캡처. control 2종, reference, base, C1/C2/C3 최대 연결성분을 모두 검출; source/clone 최대 오차 `4.93e-11 m`; physics 0 | `AUTOMATION_RENDER_PIXEL_GATE_PASS_HUMAN_CHECK_REQUIRED`. 이전 실패의 단일 원인은 여러 렌더-path 수정을 함께 적용해 미분리. 사람 GUI 확인 전 physics 차단 유지 |
| 2026-10-03 | 29806 | 정적 gate 사람 확인 | 내부 pixel gate와 동일 실행의 GUI에서 회색 base, 분리된 빨강/초록/파랑 문, reference/control을 사람이 확인. 이전 흰 면·선·분리 판 없음 | `STATIC_MAPPING_AUTOMATION_AND_HUMAN_PASS`; physics step 0이며 물리/영상 성공으로 확대하지 않음 |
| 2026-10-03 | 29806 | 물리 runner 감사 | 물리 분기에서 `settings` 초기화 누락, linked clone pre-physics pixel gate 부재, validator record 기대값 900/실제 설정 1350 불일치 발견 | settings 공통 초기화, body-local linked clone 내부 pixel gate, 3/4 camera, 1350-record validator, 문별 drift/화면 변화, 파생 MP4/GIF 검증을 추가. 실제 host 실행 전 상태 |
| 2026-10-03 | 29806 | 첫 end-to-end GUI physics | pre-physics pixel PASS 뒤 450 pretest steps를 9.079초에 처리. 사람은 초기 문 소실/재등장과 매우 빠른 세 문 동작을 관찰. MP4/ffmpeg/대표 프레임/성공 marker 없음. inactive drift 검사에서 예외 | `INVALID_FAST_VISUAL_AND_INACTIVE_DOF_DRIFT`; 실패 staging만 보존, 공식 영상 승격 금지 |
| 2026-10-03 | 29806 | 실패 원인 감사 | 기존 inactive drift는 verified settle baseline 없이 nominal target과 비교했고 target vector를 target block마다 한 번만 전송. 초기화 후 pixel 표본이 없어 문 소실 step은 미확정 | 매-step 3-DOF target, 실측 settled baseline, 60 Hz wall pacing, smoothstep, initialize/step 0·1·2·5·10 visual continuity gate로 교체 |
| 2026-10-03 | 29806 | drift 판정 보완 | baseline excursion만으로는 closed target에서 멀리 안정된 상태를 통과시킬 수 있고 `0.02 rad`는 기존 headless 관측 `0.000108 rad`보다 크게 느슨함 | closed-target absolute error `≤0.01 rad`와 다른 문 구동 중 baseline excursion `≤0.002 rad`를 분리. 자기 active/settle 제외, 30연속 안정·300-step timeout, root `≤1e-4 m/0.002 rad`로 실행 전 고정 |
