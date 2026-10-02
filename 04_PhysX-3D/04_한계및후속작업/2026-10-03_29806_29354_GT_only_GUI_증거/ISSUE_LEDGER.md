# Issue ledger

| 시각 | 사례 | 단계 | 증상/상태 | 판정 |
|---|---|---|---|---|
| 2026-10-03 | 공통 | 준비 | 기존 사용자 untracked 파일 다수 확인 | 건드리지 않고 새 폴더만 사용 |
| 2026-10-03 | 29806 | 입력 gate | USD SHA256과 기존 Git 기록 일치 | 입력 확인 완료, GUI/physics 미실행 |
| 2026-10-03 | 29354 | 입력 gate | USD SHA256과 기존 Git 기록 일치 | 입력 확인 완료, GUI/physics 미실행 |
| 2026-10-03 | 29806 | 첫 shell gate | `STRUCTURE_GATE_PASS_PHYSICS_NOT_STARTED`라는 이름과 달리 Isaac composed stage는 열지 않음 | 범위를 입력/GPU/X11 gate로 정정. 새 runner 내부에 실제 composed mapping gate 추가 |
| 2026-10-03 | 29806 | 첫 GUI physics/capture | 사람 화면에서 길쭉한 base와 한 판만 뚜렷하며 세 문 독립 구조가 식별되지 않음. 자동 validator도 `FAIL` | `INVALID_VISUAL_MAPPING`; MP4 SHA `d6a2759f...`는 staging에만 격리, 공식 링크/GIF 금지 |
| 2026-10-03 | 29806 | mapping 기록 감사 | body 관계와 Mesh component는 분리됐으나 모든 clone이 같은 색이고 marker에 원래 ancestor 및 world bounds 비교가 없음 | 물리 없는 회색 base + 빨강/초록/파랑 door static gate로 교체 |

실행 오류는 같은 명령을 반복하지 않고 `LOG_DIR`, 최초 예외, physics 시작 전/후 여부를 새 행으로 기록한다.
