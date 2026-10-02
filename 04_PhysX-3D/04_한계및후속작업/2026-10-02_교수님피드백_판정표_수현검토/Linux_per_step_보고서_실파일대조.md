# Linux 보존 per-step 보고서 실제 파일 대조

작성 범위: Git의 GT-only 실행 요약/README가 보존한 Linux per-step 보고서의 절대 경로와 SHA256을 실제 staging 파일에 대조했다. 새 Isaac 실행, 추론, 렌더링, 재생성은 수행하지 않았다.

판정 규칙: Git 기록에 절대 경로 또는 SHA256이 없으면 실제 파일을 발견했더라도 기대값을 추정하지 않고 `MISSING_RECORD`으로 표기한다. 따라서 29354의 실제 내용 대조는 가능하지만, Git 기록 기반 경로·SHA256 대조는 완료로 처리하지 않는다.

## 파일 대조

| 사례 | Git 기록 출처 | Git 기대 절대 경로 | Git 기대 SHA256 | 실제 절대 경로 | bytes | 실제 SHA256 | 경로·해시 판정 |
|---|---|---|---|---|---:|---|---|
| 10163 | README.md | `/home/minsujo/Desktop/SH/PHYSx/staging/gt-only-isaac-tensor-drive-20261002T105035Z-10163-tensor-drive/physics_drive_report.json` | `7e09c7d658f37ffa15761f0d37b2a7c97eb9a9759b41b8e6597a5a412144f610` | `/home/minsujo/Desktop/SH/PHYSx/staging/gt-only-isaac-tensor-drive-20261002T105035Z-10163-tensor-drive/physics_drive_report.json` | 3,008,953 | `7e09c7d658f37ffa15761f0d37b2a7c97eb9a9759b41b8e6597a5a412144f610` | `MATCH` |
| 29806 | summary.json / README.md | `/home/minsujo/Desktop/SH/PHYSx/staging/gt-only-isaac-tensor-drive-20261002T110246Z-29806-tensor-drive/physics_drive_report.json` | `acc3989b87682d1534db13fd06aae6b190cf2df6fa362551e882bf518a518426` | `/home/minsujo/Desktop/SH/PHYSx/staging/gt-only-isaac-tensor-drive-20261002T110246Z-29806-tensor-drive/physics_drive_report.json` | 59,594,413 | `acc3989b87682d1534db13fd06aae6b190cf2df6fa362551e882bf518a518426` | `MATCH` |
| 29354 | summary.json / README.md: per-step report absolute path and SHA256 absent | `MISSING_RECORD` | `MISSING_RECORD` | `/home/minsujo/Desktop/SH/PHYSx/staging/gt-only-isaac-fixed-20261002T113459Z-29354-fixed/report.json` | 29,371 | `ae08ed5fe2a83d7f500c22cc5b8ebfeda37ff472555f656dcde2cec4cf74e9e2` | `MISSING_RECORD` |

## 실행 범위 대조

| 사례 | 실제 보고서에서 확인한 범위 | Git summary/README와의 대조 | 사례 판정 |
|---|---|---|---|
| 10163 | `records` 2,640건: 초기화 3회 × 60 = 180건, in-range 10회 왕복 × 5 target × 2 방향 × 24 step = 2,400건, out-of-range 60건. `checks.finite=true`; target 5개 `[-1.2,-0.6,0,0.6,1.2]` rad. | `summary.json`의 2,400/180/60 및 10 round trips·3 resets와 일치. README의 보고서 SHA256과 실제 SHA256 일치. | `VERIFIED_MATCH` |
| 29806 | 각 `gt_C_1`, `gt_C_2`, `gt_C_3`에 target 5개, `initializations` 180건, `roundtrips` 2,400건, `out_of_range` 60건. 전체 `all_records` 7,920건; 각 joint `checks.finite=true`. | `summary.json`의 joint별 2,400/180/60, 10 round trips·3 resets 및 보고서 경로/SHA256과 일치. | `VERIFIED_MATCH` |
| 29354 | 실제 로컬 보고서 `records` 180건, `preflight.dof=0`, `finite=true`, `max_observed_link_translation_drift_m=1.0280995564419422e-07`. | `summary.json`의 passive 180 steps, DOF 0, finite, drift 값과 내용은 일치. 그러나 Git summary/README에는 원본 per-step report 절대 경로와 SHA256이 기록되지 않았다. | `MISSING_RECORD` (내용 대조만 가능) |

## 체크박스 처리

세 사례 모두의 **Git 기록 기반 경로·SHA256** 대조가 완료된 것은 아니다. 29354가 `MISSING_RECORD`이므로 상위 `README.md`의 “Linux 보존 per-step 보고서의 경로·SHA256을 실제 파일과 다시 대조” 체크박스는 변경하지 않았다. 승민 교차검토 체크박스도 변경하지 않았다.

## 한계

- 이 기록은 Linux staging에 보존된 보고서 파일과 Git의 작은 요약 기록의 무결성·레코드 수 대조다.
- GT-only 물리 구동의 의미, 자동 예측군 성능, 또는 Isaac/PhysX 재실행 성공을 새로 주장하지 않는다.
