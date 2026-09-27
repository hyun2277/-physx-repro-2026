# PhysX-3D 중간 재현 보고서 — public-only v1, 11 표본

본 보고서는 공개 자료 기반 독립 평가이며 논문 Table 2 또는 논문 동일 1,000-test 재현이 아니다. 기존 artifact를 다시 생성하지 않고 CPU 검산만 수행했다.

## 범위와 실행 상태

- 원본 공식 table 예제 1건은 기존 기록상 성공했다.
- RTX 5090 결과는 CUDA 12.8/GCC 12 및 검증된 channel-tiled Native adapter와 sampling/decoder 분리 경로를 사용한 환경 적응 실행이다. 따라서 원본 단일 프로세스 실행과 비트 동일하다고 주장하지 않는다.
- 11개 artifact-complete 표본의 geometry·scale·official group-count diagnostic만 public-only v1로 집계했다.

## 11 표본 결과

| ID | class | raw CD L1 | canonical CD L1 | raw F-score | scale error (cm) | GT/pred groups | diagnostic |
|---|---|---:|---:|---:|---:|---|---|
| 29354 | fixed | 0.249268 | 0.125875 | 0.358931 | 20.211433 | 1/2 | count diagnostic only |
| 24566 | B_translation | 0.205685 | 0.201994 | 0.379456 | 26.331444 | 2/1 | false negative |
| 29806 | C_rotation | 0.350371 | 0.071316 | 0.000000 | 15.045036 | 4/2 | multi-joint underprediction |
| 21356 | fixed | 0.330629 | 0.310282 | 0.227628 | 10.544861 | 1/1 | count diagnostic only |
| 27703 | fixed | 0.310763 | 0.177194 | 0.157830 | 26.803574 | 1/1 | count diagnostic only |
| 30719 | fixed | 0.633599 | 0.562961 | 0.071207 | 21.886841 | 1/1 | count diagnostic only |
| 21314 | fixed | 0.368723 | 0.152682 | 0.171297 | 12.552658 | 1/1 | count diagnostic only |
| 32980 | fixed | 0.378598 | 0.102092 | 0.060909 | 2.952049 | 1/1 | count diagnostic only |
| 48419 | B_translation | 0.315815 | 0.221268 | 0.096110 | 3.214561 | 4/1 | false negative |
| 38882 | B_translation | 0.369965 | 0.168751 | 0.155224 | 12.338470 | 7/2 | multi-joint underprediction |
| 15821 | C_rotation | 0.325098 | 0.572538 | 0.176056 | 0.191544 | 2/1 | false negative |

## 집계와 한계
- Overall n=11; fixed/B/C 분모는 6/3/2다. Raw와 canonical geometry는 별도 조건이며 평균으로 섞지 않았다.
- Overall raw CD L1 mean=0.348956; canonical CD L1 mean=0.242450; scale error mean=13.824770 cm.
- 23787은 official retrieval non-finite OBJ, 27281은 보존된 28,000 MiB/4,607 MiB 조건의 mesh decoder OOM, 14567은 source MTL `map_Kd` 부재로 수치 분모 밖에 유지했다.
- Density·affordance·description map PSNR와 NAP COV/MMD는 GT/pred map·mask·part mapping·question/NAP conversion·공식 집계 규약 부재로 blocked다.
- 30-view paper condition, GT vertex correspondence, parent/axis/range 정확도, 물리 정확도는 주장할 수 없다.

## 현재 주장 가능한 것

- 11개 기존 artifact의 무결성·유한성과 public-only geometry/scale/group diagnostic 계산 규약은 이번 독립 검산에서 확인됐다.
- 24566은 GT 2 groups 대비 official 1 group으로 false negative, 29806은 GT 4 groups 대비 official 2 groups으로 multi-joint underprediction이라는 표본 단위 count diagnostic은 재확인됐다.

## 다음 선택지

A. 이 11표본 public-only v1 결과를 중간 재현 보고서로 확정한다.
B. 새 ShapeNet category 확보 후 사전 목록을 고정하고 20–30 표본 independent evaluation으로 확장한다. 이 확장도 공식 evaluator 자료가 없으면 Table 2 비교가 아니다.
