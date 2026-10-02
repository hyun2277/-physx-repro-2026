# 김승민 팀원 제공 초안과 최신 기록의 교차검토

## A. 김승민 팀원 제공 초안의 검토 범위

- 외부 제공 파일: `김승민_1002_검토-20261002T121816Z-1-001.zip` (Git에 추가하지 않음).
- 읽은 파일은 ZIP 내부 `README.md`, `case_table.csv`뿐이다. `verify_and_commit.sh`는 실행하지 않았다.
- 초안 작성일은 문서에 적힌 2026-10-02다. 초안의 `[G]`는 당시 GitHub main 문서에서 직접 대조한 항목, `[U]`는 실행 담당자 보고 또는 TODO 로그 대조 전 항목으로 구분되어 있다.
- 본 기록은 초안 원문을 수정하거나 `[U]`를 김승민 본인의 `[G]`로 소급 변경하지 않는다. 아래 B절은 **Codex의 최신 Git·Linux 원본 보고서 후속 대조**다.

초안이 직접 확인했다고 표시한 범위는 generated-output 관절 명세의 해석 한계, GT-only와 자동 예측군의 구분, 10163·29806·29354의 기본 group 판정, 수동 보정 미수행, 일부 결과보기 영상의 성격이다. 초안에서 `[U]` 또는 TODO로 남긴 범위는 GT-only Isaac 실행의 실제 원본 보고서, 정확한 실행 로그 경로·해시, 3사례 판정표의 최신 반영, viewport/Replicator 결과다.

## B. 최신 Git·Linux 원본 로그 후속 대조

기준 `origin/main`: `cc89e78782743581521aa9ba3b7b5358ac45e321`. local HEAD와 원격 `main`도 이 SHA였다.

| 후속 대조 항목 | 근거 | 결과 | 김승민 초안과의 관계 |
|---|---|---|---|
| 10163 GT-only Tensor drive | `20261002T105035Z_10163_GT_only_물리구동_결과/README.md`, `summary.json`, Linux 보고서 대조 | GT-only PASS, 1 DOF, 5 targets, 10 round trips, 3 resets; 실제 3,008,953-byte 보고서 SHA256 `7e09…f610`이 Git README 기록과 일치. | 초안의 `[U]` 실행/PASS는 **후속 근거로 대조됨**; 김승민 본인 `[G]`로 변경하지 않음. |
| 29806 GT-only Tensor drive | `20261002T110246Z_29806_GT_only_물리구동_결과/README.md`, `summary.json`, Linux 보고서 대조 | GT-only PASS, revolute DOF 3개를 각자 5 targets, 10 round trips, 3 resets; 59,594,413-byte 보고서 SHA256 `acc3…8426` 일치. | 초안의 `[U]` 실행/PASS 및 3 joint는 **후속 근거로 대조됨**. |
| 29354 GT-only fixed passive control | `20261002T113459Z_29354_GT_only_고정대조군_결과/README.md`, `summary.json`, Linux 보고서 대조 | passive 180 steps, DOF 0, finite, 최대 drift `1.0280995564419422e-07 m`가 실제 report와 내용 일치. Git summary/README에는 report 절대 경로·SHA256이 없음. | PASS 내용은 **후속 내용 대조됨**; Git 기록 기반 경로·해시는 `MISSING_RECORD`으로 남김. |
| 생성 결과 관절 명세 | `2026-09-29_생성결과_관절명세_감사/README.md`, `joint_field_matrix.csv` | 10163·29806은 `INTERPRETATION_BLOCKED`; 29354는 `NO_DEPLOYABLE_JOINT_SPEC`. parent/axis/origin/limit을 GT로 채우지 않았다. | 초안의 `[U]` 판정·구체 이유는 최신 Git으로 대조됨. |
| GT converter의 입력 | 같은 관절 명세 감사의 `urdf_gen.py` 추적 | `finaljson/group_info/partseg` GT를 읽는 GT 대조군 도구다. generated output 자동 변환기가 아니다. | 초안의 `[G]`와 대조 범위에서 불일치 발견 못 함. |
| 10163 viewport/Replicator RGB | `RENDER_RECOVERY_BLOCKED.md`, commit `02e40bd079f8ad1258beefc48d0c5731c60ac021`의 Replicator 차단 기록 | 기존 viewport MP4는 `INVALID_BLACK_CAPTURE`. Replicator PNG 3장도 RGB 평균·분산·최대가 모두 0인 완전 검정이라 `BLOCKED_RGB_BLACK`. 정상 3D physics 영상 없음. | 초안의 `[U]` 영상 한계는 후속 Git 대조로 확인됨. state-trace는 logged physics state 그래프이며 3D mesh 영상이 아님. |
| 사람 시간·수동 보정 | 수현 판정표 README | 수동 보정은 `미수행`; 보정 시간은 `N/A(해당 없음)`. 과거 관절 명세 조사 사람 시간은 `미기록/확인 불가`; Codex 시간을 사람 시간으로 환산하지 않음. | 초안의 `0분`을 바로잡음. |

원본 per-step 파일 대조의 상세 경로·bytes·expected/actual SHA256은 [Linux per-step 대조 기록](../2026-10-02_교수님피드백_판정표_수현검토/Linux_per_step_보고서_실파일대조.md)에 있다. 29354의 `MISSING_RECORD`은 Git의 summary/README에 기대 경로·해시가 없다는 뜻이며, 실제 발견한 파일의 해시를 Git 기대값으로 추정한 것이 아니다.

### 발견한 수정 사항

1. 외부 초안의 수동 보정 시간 `0분`은 성공 또는 측정값으로 읽힐 수 있어 `N/A(해당 없음)`으로 정정했다. 수동 보정은 **미수행**이다.
2. 외부 초안의 10163·29806·29354 GT-only 실행과 결과는 당시 `[U]`였으나, 최신 Git 및 Linux 원본 보고서로 후속 근거를 대조했다. 이 변경은 김승민의 직접 확인 표기를 바꾸지 않는다.
3. 29354의 per-step report는 실제로 읽혀 passive 180/DOF 0/finite/drift 내용이 맞지만, Git 기록에 원본 report 경로·SHA256이 없다. `MISSING_RECORD`을 유지한다.

## C. 최종 판정표

| 사례 | 군 | 상태 | 실행 상태 | 사실 범위 | 수동 보정/시간 | 영상 상태 |
|---|---|---|---|---|---|---|
| 10163 | 자동 예측군 | `INTERPRETATION_BLOCKED` | Isaac 미실행 | group 1은 5 vertices; parent/type/axis/origin/limit을 해석 가능한 generated contract로 만들 수 없음 | 미수행 / N/A(해당 없음) | 정상 3D physics 영상 없음 |
| 10163 | 수동 보정군 | `NOT_PERFORMED` | 미실행 | GT 값을 예측 필드에 복사·보완하지 않음 | 미수행 / N/A(해당 없음) | 해당 없음 |
| 10163 | GT-only 대조군 | `PASS` | 실행 | GT converter·Isaac Sim controlled-material tensor drive PASS; AI 예측 결과 아님 | 미수행 / N/A(해당 없음) | state-trace는 실제 joint-state 그래프; viewport MP4는 `INVALID_BLACK_CAPTURE` |
| 29806 (006) | 자동 예측군 | `INTERPRETATION_BLOCKED` | Isaac 미실행 | predicted groups 3, 의미 있는 moving region 1; GT 3문 복원·joint parameter 정확도는 미검증 | 미수행 / N/A(해당 없음) | 정상 3D physics 영상 없음 |
| 29806 | 수동 보정군 | `NOT_PERFORMED` | 미실행 | GT parent/axis/origin/range를 보완에 사용하지 않음 | 미수행 / N/A(해당 없음) | 해당 없음 |
| 29806 | GT-only 대조군 | `PASS` | 실행 | GT revolute 3 DOF를 독립 tensor drive; AI 예측 성공 아님 | 미수행 / N/A(해당 없음) | state-trace는 실제 joint-state 그래프 |
| 29354 | 자동 예측군 | `NO_DEPLOYABLE_JOINT_SPEC` | Isaac 미실행 | retained 14-channel property head 없음, 극소 false group; 실행 가능한 관절 명세 없음 | 미수행 / N/A(해당 없음) | 해당 없음 |
| 29354 | 수동 보정군 | `NOT_PERFORMED` | 미실행 | 수동 성공 사례를 만들지 않음 | 미수행 / N/A(해당 없음) | 해당 없음 |
| 29354 | GT-only 대조군 | `PASS` | 실행 | GT fixed passive control, DOF 0, joint target 없음; AI 예측 결과 아님 | 미수행 / N/A(해당 없음) | 해당 없음 |

GT-only PASS는 **GT 변환기·Isaac Sim 물리 제어 대조군 PASS**일 뿐 AI 예측 관절 성공, generated-output 자동 변환 성공, 예측 물성 정확도 검증이 아니다. 10163·29806 자동 예측군은 Isaac에서 실행하지 않았다.

## D. 교차검토 완료 범위와 남은 항목

- 김승민 팀원 제공 초안의 범위: 초안의 `[G]/[U]/TODO` 구분과 사례별 해석을 보존해 검토했다.
- Codex 후속 대조 범위: 최신 Git 기록, 10163·29806·29354 GT-only summaries/readmes, generated joint-field audit, black viewport/Replicator block 기록, Linux per-step report의 경로·SHA256 및 record count 대조를 확인했다.
- 수현 검토 기록과의 관계: 자동 예측군 `INTERPRETATION_BLOCKED`/`NO_DEPLOYABLE_JOINT_SPEC`, GT-only와 자동 예측군 분리, 수동 보정 미수행은 대조 범위에서 불일치 발견 못 함. 29354의 Git 기반 per-step path/SHA256는 두 기록 모두 `MISSING_RECORD`이다.
- 여전히 미확인: generated-output의 공개 joint coordinate frame·unit·denormalization·group-to-link contract, AI 예측군 Isaac 실행, 정상 3D mesh physics 영상, contact-force 정확도, 사람의 과거 관절 명세 조사 능동 작업시간.

수현 검토 README의 김승민 체크박스는 변경하지 않았다. 이 외부 초안에는 김승민의 직접 검토 범위와 `[U]` 한계가 남아 있으며, 이 후속 대조는 Codex가 수행한 별도 범위이기 때문이다.
