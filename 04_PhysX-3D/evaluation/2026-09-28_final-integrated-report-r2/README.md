# PhysX-3D 최종 통합 보고서 r2 — 2×RTX 5090 환경

기준 시점: 2026-09-28. 이 문서는 기존 최종 통합 보고서와 adapter fidelity suite,
tile sensitivity v2의 고정 기록을 읽기 전용으로 대조한 개정판이다. 새 GPU 실행,
추론, 렌더링, 다운로드, 설치, 학습 또는 기존 artifact 변경은 수행하지 않았다.

## 결론을 구분하는 기준

| 구분 | 확인된 범위 | 이 보고서에서 주장하지 않는 범위 |
|---|---|---|
| 원본 공식 실행 | 고정 source `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`에서 table 예제 1건이 종료 코드 0과 기본 산출물 검증까지 성공했다. | 논문 전체 재현, test 성능, 정량 정확도 |
| RTX 5090 환경 적응 | CUDA 12.8.1 overlay, GCC 12, GPU 1 보호, runtime sparse adapter로 public-only v1 artifact를 만들었다. | 원본 CUDA 11.8 전체 환경·단일 process의 비트 단위 동등성 |
| adapter fidelity | tested local GPU cases에서 channel/output tiling, streaming GroupNorm, decoder child 분리가 수치 허용범위 안이었다. 총 판정은 **`partially_verified`**다. | int32 초과 production layer의 원본-path 직접 비교, 25표본 모든 layer/branch trace, Table 2 동등성 |
| public-only v1 | 25 artifact-complete 표본의 geometry·scale scalar·official group-count/moving-surface diagnostic을 제안 규약으로 계산했다. fixed/B/C는 **15/5/5**다. | 논문 Table 2, PSNR·description·NAP, 물리·관절 정확도 일반화 |
| 후속 benchmark/simulation | PhysX-Bench tiny smoke와 25-row DQS manifest는 준비됐다. generated-only URDF/USD/Isaac은 contract 부재로 실행하지 않았다. | 공식 122B DQS 점수, generated asset motion 검증 |

## RTX 5090 adapter: 필요 원인과 fidelity

현재 CUDA 12.8 환경의 spconv/cumm Native 및 implicit_gemm은 큰 sparse feature에서
int32 크기 제한을 보였다. 대표 관측은 `N=2,168,704`, `C=512`, fp16이며 feature
저장량만 2,220,752,896 bytes다. 이 제한은 GPU capability 인식 문제와 별도로 다뤘다.
원본 source와 checkpoint를 바꾸지 않고 runtime adapter에서 input/output channel tiling,
원래 GroupNorm 범위를 유지하는 streaming reduction, sampling/physics/mesh child 분리를
사용했다. GPU 1만 사용하며 limit 28,000 MiB와 reserve 4,607 MiB를 고정했다.

fidelity suite (`527460d`)는 다음 local tested case를 통과했다.

| adapter | tested case | adapter 대 원본 | 상태 |
|---|---|---|---|
| channel-tiled Native SubMConv3d | actual checkpoint weight, fp16 `135,544 × 512 → 256` | max abs 3.0, relative L2 `8.0076e-4`, cosine `0.99999982` | pass |
| output-channel-tiled Native SubMConv3d | 같은 weight, input 256/output 96 forced tile | 위와 같은 수치 | pass; 25표본 성공 trace의 production fallback은 미관측 |
| memory-bounded GroupNorm | `131,072 × 256`, groups 32, 비균일 batch, fp16/fp32, affine on/off | fp16 max abs 최대 `1.9531e-3`; fp32 최대 `9.5367e-7` | pass |
| child-process 분리 | 같은 29354 cached latent/checkpoint | vertex/attr/physics max abs `1.19e-7`/`2.98e-7`/`5.96e-7`; faces exact | pass |

따라서 adapter 최종 판정은 **`partially_verified`**다. tested local cases에서는
수치적으로 가깝고 필요한 semantic screen이 안정적이지만, 원본 CUDA 11.8 전체 환경,
int32 초과 production layer의 원본 직접 경로, 25표본 전체 layer trace, 논문 Table 2
동등성은 검증되지 않았다.

## input-channel tile sensitivity

tile sensitivity v2 (`0e93c58`)는 기존 artifact를 덮지 않는 새 staging에서 29354와
29806 각각에 대해 baseline `tile_channels=256`, 독립 256 control, `tile_channels=128`을
같은 conditioning `000.png`, checkpoint, seed 1, GPU 1, Native spconv, CUDA overlay,
output tiling, GroupNorm 및 child 분리 조건으로 실행했다.

같은 tile=256 control에서도 CUDA 자체의 latent와 mesh topology 차이가 관찰됐다. 예를
들어 physics latent relative L2(control)는 29354 `0.00123175`, 29806 `0.00466420`이다.
따라서 tile 차이를 단독 원인으로 과장하지 않았고, topology가 달라 vertex row-wise
비교가 불가능한 경우에는 deterministic surface diagnostic·scale·group screen을 별도로
기록했다.

| 표본 | 128 대 256 physics latent relative L2 | channel adapter 실사용 trace | group/표면 결과 | 판정 |
|---|---:|---|---|---|
| 29354 fixed | `0.00121284` | 실제 큰 Native `N=2,168,704, C=512, O=256` 호출에서 256·128 각각 2회 | 공식 group 수 모두 2; group 1은 모두 homogeneous face 0인 비의미적 극소 영역 | `numerically_different_but_semantically_stable` |
| 29806 C rotation | `0.00606931` | 해당 입력에서는 int32 초과 channel adapter 호출이 없음 | 공식 group 수 모두 2; group 1 면적 비율 256/control/128 = `0.12471/0.12520/0.12280`, component = `126/124/120` | `numerically_different_but_semantically_stable` |

29354에서는 channel tiling이 bitwise 동일하지 않지만 256과 128이 같은 group 판정과
비의미적 극소 moving 영역을 보였다. 29806도 256/128에서 같은 공식 group 수와 비슷한
moving surface를 보였지만, 이 표본은 int32 초과 channel adapter가 실제로 필요했던
표본이 아니다. 둘 다 adapter 전체의 완전 동등성 또는 논문 Table 2 동등성을 뜻하지 않는다.

## public-only v1: 25표본 독립 평가

이는 **공개 자료 기반 독립 평가 v1**이며 논문 Table 2 동일 평가가 아니다. area-weighted
barycentric sampling(PCG64), mesh당 8,192 점, symmetric CD L1/L2, threshold 0.05
F-score를 사용한다. raw coordinate와 bbox-center/max-extent canonical 결과는 분리했고
평균내지 않았다. scale은 GT JSON dimension maximum과 predicted vertex scale mean의
scalar diagnostic이다. group은 official group count와 predeclared moving-surface
screen일 뿐 GT part와 정점 대응을 만들지 않는다.

기존 25표본 macro 결과는 raw CD L1 `0.365911`, raw CD L2 `0.107425`, raw F-score
`0.166900`, canonical CD L1 `0.245966`, canonical CD L2 `0.055724`, canonical
F-score `0.349543`, scale absolute error `17.913852 cm`, group-count absolute error
`0.68`이다. 이 숫자를 논문 Table 2와 비교하지 않는다.

| class | complete | 확인된 예시 | 한계 |
|---|---:|---|---|
| fixed | 15 | 29354는 `num_group=2`이나 group 1은 극소 영역이다. | group count가 실제 관절을 뜻하지 않는다. |
| B translation | 5 | 24566은 GT drawer 2 groups 대비 official prediction 1 group인 false negative다. | generated mesh↔GT part 대응이 없다. |
| C rotation | 5 | 29806은 GT 4 groups 대비 000.png 2 groups, 동일 seed 006 probe 3 groups였다. | 단일 표본·두 view의 질적 probe다. |

23787·27370은 official retrieval non-finite OBJ, 14567은 MTL `map_Kd` texture 부재,
27281은 고정 memory policy 아래 mesh decoder OOM으로 failure/exclusion ledger에
남으며 25표본 metric 분모에 넣지 않았다.

## 차단된 항목과 Issue #18

generated-only URDF/USD/Isaac은 공개 contract 부재로 차단됐다. 공식 `urdf_gen.py`는
GT JSON/part OBJ와 GT parent/type/axis/origin/range를 읽는다. generated output에는
검증된 joint parameter, collision, mass/density/inertia contract가 없다. GT field를
복사·보완하지 않는 규칙 때문에 conversion과 Isaac smoke test를 시작하지 않았다.

PhysX-Bench tiny smoke는 synthetic manifest/aggregation/denominator validation만
성공했고, DQS 입력 manifest 25행은 준비됐다. `scale.npy`는 predicted vertex mean을
cm float64 scalar로 내보낸 proposed conversion이다. 공식 기본 VLM
`Qwen/Qwen3.5-122B-A10B`는 BF16 weight만 약 227 GiB가 필요하다. 2×RTX 5090의 약
64 GiB aggregate memory에는 runtime overhead 전부터 들어가지 않아 official DQS VLM은
`BLOCKED_BY_HARDWARE_OR_MODEL`이다. quantized 또는 다른 VLM은 공식 pilot과 다르다.

논문 동일 Table 2는 공개 evaluator/config, test conditioning manifest, 30-view
camera/transforms/mask, GT material/affordance/description maps, mesh↔GT part 대응,
kinematics/NAP conversion과 duplicate/failure aggregation 규약이 확정되지 않아
차단됐다. 현재 24-view render_cond는 논문 외관 평가의 30-view 조건과 다르다.
GitHub Issue [#18](https://github.com/ziangcao0312/PhysX-3D/issues/18)에 이 공개 위치와
규약을 문의했다. 답변 전에는 이 빈칸을 채운 Table 2 평가를 할 수 없고, existing
artifact hash audit·public-only CPU 재집계·DQS manifest 유지 정도만 가능하다.

## 현재 주장 가능성과 재개 조건

### 현재 2×RTX 5090에서 주장 가능한 결론

1. 공식 table 예제 1건과 RTX 5090 adapter 기반 public-only artifact 생성은 각각
   기록된 범위에서 성공했다.
2. tested local adapter case는 수치적으로 가깝고, 29354의 실사용 256/128 tile probe는
   같은 group/비의미 moving-area screen을 유지했다. 이는 `partially_verified` 범위다.
3. 25표본의 공개자료 기반 independent geometry·scale·group diagnostic과 PhysX-Bench
   DQS 입력 준비는 가능하지만 논문 Table 2나 official DQS score가 아니다.

### 외부 A100/H100 또는 저자 답변 뒤에만 가능한 결론/작업

1. 충분한 aggregate BF16 memory와 official runtime 설정에서 unmodified official DQS
   VLM을 실행한다. 단일 80 GiB A100/H100이 122B BF16에 충분하다고 가정하지 않는다.
2. 저자 답변 또는 공개 release로 evaluator, input/camera/GT mask manifest와 NAP
   aggregation이 확보된 뒤 논문 규약 평가를 별도 고정 환경에서 수행한다.
3. generated-only joint contract가 공식적으로 제공·검증된 뒤 GT 보완 없이 URDF/USD와
   Isaac/MuJoCo motion smoke를 실행한다.

## 참조

모든 경로와 SHA256은 [reference_hashes.json](reference_hashes.json)에 고정했다.
기존 최종 보고서는 수정하지 않았고, 이 r2만 최신 adapter evidence를 반영한다.
