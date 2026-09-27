# PhysX-3D 최종 통합 보고서 — 2×RTX 5090 환경

기준 시점: 2026-09-27. 이 문서는 현재 Linux의 RTX 5090 두 장이 사용할 수
있는 최대 GPU 환경이라는 전제에서, 기존 실행 기록과 작은 결과 파일만 다시
대조해 만든 통합 보고서다. 새 GPU 실행, 추론, 렌더, 다운로드, 학습, 데이터 변경은
수행하지 않았다.

## 결론의 적용 범위

| 구분 | 확인된 사실 | 이 보고서에서 말할 수 없는 것 |
|---|---|---|
| 원본 공식 table 예제 | 고정 공식 source `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`에서 table 예제 1건이 종료 코드 0과 기본 산출물 검증까지 성공했다. | 논문 전체 재현, test 집합 성능, 정량 정확도 |
| RTX 5090 환경 적응 | CUDA 12.8.1 overlay, GCC 12, GPU 1 보호와 runtime sparse adapter로 29354 및 public-only 표본의 mesh·raw physics 출력을 생성했다. | 원본 단일 프로세스 native 실행과 비트 단위 동일성, 논문 조건 동일성 |
| public-only v1 독립 평가 | artifact-complete 25개에서 제안 규약의 geometry, scale scalar, official group-count/moving-surface diagnostic을 계산했다. class 구성은 fixed/B/C = 15/5/5다. | 논문 Table 2 수치, PSNR·description·NAP 성능, 물리·관절 정확도 일반화 |
| PhysX-Bench 준비 | 공식 tiny smoke test는 성공했고, 25개 DQS 입력 manifest는 준비·검증됐다. | 공식 DQS VLM 점수, 다른 PhysX-Bench 지표 점수 |
| generated-only URDF/USD/Isaac | 생성 output만으로는 검증된 joint contract가 없어서 변환과 Isaac smoke test를 시작하지 않았다. | 생성 asset의 관절 동작, 제조/시뮬레이션 자산 적합성 |

## RTX 5090 환경 적응의 이유와 검증 범위

현재 `physxgen` CUDA 12.8 환경의 spconv/cumm native 및 implicit_gemm 경로는 큰
sparse feature 연산에서 int32 크기 제한을 보였다. 관측된 대표 크기는
`N=2,168,704`, `C=512`, fp16으로, feature 저장량만 `2,220,752,896` bytes다.
이 문제는 GPU capability 인식 문제와 구분하여 다뤘다.

원본 source와 checkpoint는 바꾸지 않고 별도 runtime adapter에만 다음을 적용했다.

* 원래 sparse 연산과 작은 독립 reference의 사전 동등성 검사를 통과한 경우에만
  입력/출력 channel tiling을 적용했다.
* GroupNorm의 정규화 범위를 바꾸지 않는 streaming fp32 reduction을 사용해 전체
  fp32 복사본 peak를 피했다.
* sampling, physics decoder, mesh decoder를 다른 child process로 분리했다.
* GPU 1만 사용했고, hard limit 28,000 MiB 및 reserve 4,607 MiB를 고정했다.

따라서 29354 mesh·raw vertex physics 생성과 25개 public-only artifact 생성은
**RTX 5090 환경 적응 실행 성공**이다. 이는 adapter의 작은 수치 검증과 output
유한성·mesh reload를 확인한 범위이며, 원본 경로의 비트 단위 재현이나 논문 Table 2
재현이 아니다.

## public-only v1 25표본

평가 규약은 deterministic area-weighted barycentric sampling(PCG64, seed
`20260927`, mesh당 8,192점), symmetric CD L1/L2, Euclidean threshold 0.05의
F-score를 사용한다. raw coordinate와 각 mesh의 bbox center/max extent canonical
정규화는 별도 결과이며 서로 평균내거나 섞지 않았다. scale은 공식 GT render code가
쓰는 JSON dimension 최대값과 기존 official-code audit의 predicted vertex mean을
비교하는 scalar diagnostic이다. group diagnostic은 공식 group index 결과와 사전에
고정한 meaningful-moving-surface 기준을 기록한다.

25개 전체 결과 파일의 기존 overall 값은 raw CD L1 `0.365911`, raw CD L2
`0.107425`, raw F-score `0.166900`, canonical CD L1 `0.245966`, canonical CD L2
`0.055724`, canonical F-score `0.349543`, scale absolute error `17.913852 cm`,
group-count absolute error `0.68`이다. 이 숫자는 제안된 공개자료 조건의 표본
macro 결과일 뿐, Table 2와 직접 비교할 수 없다.

| 계층 | artifact-complete | 관절 진단에서 확정된 예시 | 해석 한계 |
|---|---:|---|---|
| fixed | 15 | 29354의 공식 `num_group=2` 중 group 1은 정점 6개·homogeneous face 0개였다. | group 수만으로 물리적 관절을 확정할 수 없다. |
| B translation | 5 | 24566은 GT 2 groups(drawer B)이지만 공식 예측은 1 group으로 false negative다. | generated mesh와 GT part의 직접 대응이 없다. |
| C rotation | 5 | 29806은 GT 4 groups인데 000.png는 2 groups, 같은 seed의 006.png probe는 3 groups였다. 006의 추가 group 중 하나는 정점 2개여서 독립 관절로 해석하지 않았다. | 두 view의 단일 표본 질적 probe이며 일반 성능이 아니다. |

성공 표본 ID와 계층은 [sample_inventory.csv](sample_inventory.csv)에 고정했다.
기존 failure/exclusion은 [summary.json](summary.json)에 보존한다: 23787과 27370은
official retrieval output의 non-finite OBJ, 14567은 MTL `map_Kd` 부재, 27281은
고정된 28,000 MiB/4,607 MiB 정책 아래 mesh decoder OOM이다. 이 표본들은 25개
metric 분모에 포함하지 않았다.

## 생성 output 기반 URDF/USD/Isaac 차단 사유

공식 `urdf_gen.py`는 generated output을 직접 받는 converter가 아니다. GT
`finaljson/group_info`와 GT partseg OBJ를 사용하고, B/C joint의 parent, type,
axis, origin, range도 GT JSON에서 읽는다. 24566은 생성 예측이 moving group을 만들지
않았고, 29806은 GT 4 groups보다 적은 2–3 groups이며 검증된 generated
parent/type/axis/origin/range contract가 없다. 생성 mesh의 collision, mass/density,
inertia contract도 확정되지 않았다.

GT field를 generated URDF에 복사·보완하지 않는 규칙 때문에 URDF/USD를 생성하거나
Isaac을 실행하지 않았다. 이 차단은 설치 문제가 아니라 **generated-only joint
parameter contract의 부재**다.

## PhysX-Bench와 DQS 준비

PhysX-Bench source는 `46fa1cd0b6883d4d14431d51c3326ef80a85ef64`로 고정했다.
tiny smoke test는 synthetic manifest, aggregation, denominator validation만
성공했으며 VLM·GPU·PhysX-3D artifact 점수를 계산하지 않았다.

25개 DQS manifest는 공식 builder로 모두 ready가 됐다. 각 row의 existing
conditioning `000.png`와 별도 staging `scale.npy`를 연결했다. `scale.npy`는
기존 public-only scale diagnostic의 predicted vertex mean을 cm float64 scalar로
export한 **proposed conversion**이며 공식 PhysXGen 산출물이라고 부르지 않는다.

공식 DQS 기본 VLM `Qwen/Qwen3.5-122B-A10B`는 BF16 weight만 약
`122e9 × 2 = 227 GiB`가 필요하다. 두 RTX 5090은 각 32,607 MiB, 합계 약 64 GiB
이므로 runtime overhead 이전에도 충분하지 않다. benchmark runtime은
`device_map="auto"`를 사용하지만 명시 tensor parallelism을 설정하지 않으며, local
122B cache도 없었다. 이에 따라 공식 DQS VLM 상태는
`BLOCKED_BY_HARDWARE_OR_MODEL`이다. quantized 또는 다른 VLM은 nonofficial
substitute다.

## 논문 동일 Table 2 재현의 차단 조건

현재 공개 자료만으로는 다음이 확정되지 않아 논문 동일 평가를 실행하거나 주장할 수
없다.

| 필요한 항목 | 차단 내용 |
|---|---|
| 완성 evaluator/config | 공개 위치 또는 완전한 실행 규약을 확인하지 못했다. |
| test conditioning manifest | test input 이미지의 공식 선택 규약이 없다. |
| 30-view camera/transforms 및 mask | 현재 render_cond의 24-view는 논문 외관 평가 30-view 조건과 다르며, official camera seed/matrix/mask가 없다. |
| GT material/affordance/description maps·masks | pixel/vertex 대응과 PSNR range/mask/aggregation이 확정되지 않았다. |
| mesh↔GT part correspondence | generated mesh 정점과 GT part를 매칭하는 공식 규칙이 없다. |
| kinematics/NAP | group matching, coordinate frame, unit, NAP transform, duplicate/failure denominator와 aggregation 규약이 없다. |

따라서 density, affordance, description, appearance PSNR, NAP COV/MMD는 blocked다.
0점이나 임의 PSNR으로 바꾸지 않았다.

## 저자 문의와 다음 상태

공개 문의는 GitHub Issue [#18](https://github.com/ziangcao0312/PhysX-3D/issues/18)
(`Question about the released evaluation protocol and assets for PhysX-3D`)로 게시했다.
답변 또는 공개 evaluator/manifest가 나오기 전에는 위 누락 규약을 채워 Table 2
동일 평가를 할 수 없다. 반면 현재 artifact의 hash audit, public-only v1 확대,
제안 규약의 투명한 CPU 재집계, DQS manifest 유지·검증은 계속 가능하다.

## 현재 장비에서 주장 가능한 결론 3개

1. 고정 source의 공식 table 예제 1건과, 별도 adapter의 25개 public-only artifact
   생성은 RTX 5090 환경에서 각각 기록된 범위로 성공했다.
2. 25개(15 fixed, 5 B, 5 C)에는 공개자료 기반 geometry·scale·group diagnostic을
   재현 가능하게 적용할 수 있으나, 이는 논문 Table 2가 아니다.
3. PhysX-Bench tiny smoke와 25-row DQS input 준비는 가능하지만, 공식 122B BF16
   DQS VLM의 실행은 2×RTX 5090 메모리로 불가능하다.

## 외부 A100/H100 환경 또는 저자 답변 후 재개할 작업 3개

1. 여러 장의 A100/H100 등 BF16 weight 약 227 GiB와 runtime overhead를 수용하는
   충분한 aggregate memory 및 공식 runtime 설정에서, 변경 없는 official DQS VLM
   pilot을 실행한다. 단일 80 GiB GPU만으로는 충분하다고 가정하지 않는다.
2. 저자 답변 또는 공개 release로 evaluator, test conditioning/30-view camera/GT mask
   manifest가 확보되면 hash를 고정하고 논문 규약 evaluator를 별도 환경에서 실행한다.
3. generated-only kinematics contract가 공식적으로 제공되거나 검증되면, GT 보완 없이
   generated URDF/USD와 Isaac/MuJoCo motion smoke test를 분리 실행한다.

## 참조 고정값

* 공식 PhysX-3D source: `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`
* public-only v1 20 freeze tag target: `f3587b9069abac5a5b6a7dd02d3789412d3bf036`
* PhysX-Bench source: `46fa1cd0b6883d4d14431d51c3326ef80a85ef64`
* 25-sample public-only aggregate: `3292f9f7ef0013fc280e01af137ca87c813b90eefbc73606fb306bde49289869`
* DQS conversion manifest: `b853b9e58ebbe7464dbf761b6121166371e6c4b7a0331a78f04795232c0000be`
* DQS JSONL: `5392b12c088c5ef21cc45cb355e9e1425ac345138ae658294a11125f2b17e158`
