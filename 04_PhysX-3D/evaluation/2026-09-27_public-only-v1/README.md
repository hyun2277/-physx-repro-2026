# 공개 자료 기반 독립 평가 프로토콜 v1

이 결과는 **PhysX-3D 논문 Table 2의 공식 재현이나 논문 동일 평가가 아니다.** 논문 v4, 고정 source `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`, 공개 PhysXNet 원료와 기존 29354·24566·29806 산출물만 읽어 CPU에서 계산했다. 새 inference, Blender render, 다운로드, 학습은 하지 않았다.

`manifest.json`은 original `test_index`/`source_index`, ID, duplicate occurrence, 실제 GT JSON·GT mesh·generated mesh·property/audit artifact의 경로·SHA256을 보존한다. 선택 행은 29354=1, 24566=14, 29806=574다. `results.json`은 metric별 success/failed/blocked 상태와 consistency check, `records.csv`는 행별 요약, `metric_audit.json`은 9개 지표의 감사표를 제공한다.

## 제안 geometry 조건

각 mesh에서 PCG64 seed `20260927`으로 area-weighted barycentric 표면점 8,192개를 뽑는다. raw coordinate와 각 mesh를 자기 bbox center로 옮기고 max extent로 나눈 canonical coordinate를 분리한다.

- `cd_l1_sum_raw = mean(pred→GT Euclidean NN) + mean(GT→pred Euclidean NN)`
- `cd_l2_sum_raw = mean(pred→GT squared-Euclidean NN) + mean(GT→pred squared-Euclidean NN)`
- F-score는 Euclidean radius 0.05에서 양방향 hit fraction의 harmonic mean이다.
- CD `×10^-3`, F-score `×10^-2` 표시값도 raw와 함께 저장한다. 이는 논문 표 배율을 적용한 표시일 뿐 논문 수치와 비교 가능하다는 뜻이 아니다.

빈 mesh, invalid face, NaN/Inf vertex는 명시적 failure다. canonical 결과는 translation·scale을 제거하므로 absolute geometry fidelity가 아니다.

## Scale·articulation diagnostic

Scale GT는 공식 `example_render_gt_foreval.py:141–145`처럼 JSON dimension의 최대값이다. prediction은 existing property output channel 0의 vertex mean이며, 29354는 기존 official-code audit의 같은 vertex mean을 사용한다.

Official group count는 `round(max(group_id)) + 1`이다. moving group은 다음 제안 screen을 모두 만족할 때만 의미 있는 표면으로 기록한다: homogeneous face ≥100, majority-area fraction ≥0.001, largest-component vertex fraction ≥0.01. 이는 논문 관절 지표가 아니다. generated group↔GT part 대응이 없으므로 parent·direction·position·range를 평가하지 않으며 NAP COV/MMD라는 이름도 사용하지 않는다.

## PSNR·kinematics blocked

| 지표 | 상태 | 이유 |
|---|---|---|
| appearance PSNR | blocked | 논문 30-view camera, paired GT RGB, mask/range 부재; adapted decoder 결과에 texture/radiance render 없음 |
| CD/F-score | success (proposal) | 공개 evaluator가 없어 위 deterministic public-only condition만 사용 |
| scale | success (proposal/code-verified expression) | 표본 scalar 관찰만 수행 |
| density/affordance PSNR | blocked | generated vertex→GT part 대응, paired numeric map·mask·range 부재 |
| description PSNR | blocked | test 질문·part correspondence 부재, source slice 불일치 |
| kinematics COV/MMD | blocked | PhysX→NAP graph/pose/point 변환, matching, units, aggregation 부재 |

정적 감사에서 `example_render_gt_foreval.py:102–139`는 `group_info['1']`만 처리하고, `:152–155`는 current `part` 대신 이전 `meshname`으로 OBJ를 읽으며, `:161`은 seed 없는 `description_ind`를 뽑고 `:163`은 같은 `des_index.npy`를 반복 덮어쓴다. 선택 part와 저장 description의 대응은 보장되지 않는다.

`example.py:179`는 raw N×32 tensor에서 `[:,16:]`와 `[:,-16:]`라는 같은 slice를 전달하지만 training renderer는 language `[:,:16]`, physics `[:,-16:]`를 사용한다(`mesh_renderer.py:118–126`). 수정 후보를 채택하지 않았고 description은 blocked로 유지한다.

## 집계·검산

성공·failed·blocked는 지표별로 분리하고 blocked/failed를 수치 분모나 0점으로 바꾸지 않는다. 3표본 macro/micro는 진단용이며 benchmark aggregate가 아니다. `evaluation/tests/test_public_only_v1.py`는 self CD=0/F-score=1, translation raw/canonical 분리, empty/NaN failure, duplicate row 보존, articulation 규칙, status denominator 분리를 확인한다. `results.json`의 consistency check는 기존 29354 scale/fixed false positive, 24566 false negative, 29806 underprediction과의 일치를 요구한다.
