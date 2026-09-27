# PhysXNet 29354 단일 표본 의미 검증

## 범위

성공 기록 `15b527efc0fc985750cf8ab38ec06e325d7f379f`의 저장된 mesh·raw vertex physics와 기존 PhysXNet JSON·6개 part OBJ만 CPU에서 읽었다. GPU, sampling, decoder, Blender, 렌더링과 새 다운로드는 실행하지 않았다. 이 결과는 29354 한 표본의 annotation 대응 관찰이며 논문 정량평가가 아니다. 기존 24-view conditioning camera도 논문의 30-view 평가 camera로 취급하지 않았다.

## 입력 provenance

원본 annotation은 `staging/merge-29354-20260925T180423Z/physxnet/finaljson/29354.json`, part mesh는 같은 staging의 `partseg/29354/objs/{0..5}.obj`다. 병합 mesh는 `phy_dataset/29354/model.obj`, texture retrieval 결과는 `staging/retrieval-29354-20260925T183908Z/phy_dataset/29354/model_tex.obj`다. JSON SHA256은 `cf687c21110697a6ed1fc25146a8b101d789ae82acfd1b11a7e309a5b15b3600`, `model.obj`는 `2fc96114b9967a5f5fca1be77b40a5cd4c41df24671ee6da9d60c7ee9bdbb53e`, `model_tex.obj`는 `e58a15b42169119b66da9db751e25ed00c0c57d41de3db83d022538617532633`이다. 여섯 part OBJ를 포함한 전체 경로·크기·hash는 [`input_hashes.csv`](input_hashes.csv)에 있다.

## GT annotation

JSON의 `dimension`은 vector 문자열 `120*40*45`이고 단위는 annotation 생성 prompt와 논문 기록상 cm다. 공식 `merge_property.py` 141–148행 및 `example_render_gt_foreval.py` 141–145행은 숫자를 내림차순 정렬해 최대값 **120 cm**를 scalar scale GT로 사용한다.

여섯 part는 모두 material `Wood`, density `0.75 g/cm³`다. priority rank는 순서대로 1, 3, 5, 6, 7, 8이고 학습 코드의 target 식 `1-rank/10`을 적용하면 0.9, 0.7, 0.5, 0.4, 0.3, 0.2다. 원문 값과 변환값은 [`gt_part_properties.csv`](gt_part_properties.csv)에 있다.

`group_info`는 `{"0":[0,1,2,3,4,5]}` 하나뿐이다. articulated group tuple이 없으므로 parent relation, movement type, direction, position, range는 **JSON에 없다**. 이를 추정하지 않았다. `merge_property.py` 121–125행은 group 0에 대해 parent `-1`, movement parameter 여덟 개 `-1`, movement type `0`을 파생 기본값으로 만들지만 이는 JSON에 기록된 관절 GT가 아니다. 공식 데이터 변환 규칙상 29354는 fixed object다. 구조화 결과는 [`gt_annotation.json`](gt_annotation.json)에 있다.

## 예측 group의 실제 크기와 연결성

공식 physics output head와 `example.py`의 threshold를 그대로 CPU 적용했다. group 0은 `-0.5 < group_id < 0.5`, group 1은 `0.5 < group_id < 1.5`다. 공식 object-level 분기는 `round(max(group_id))+1`을 사용한다. max가 0.516207이므로 `num_group=2`, 즉 코드 분기는 fixed가 아니다.

그러나 0.5 이상 정점은 381,856개 중 **6개(0.001571%)**뿐이다. 0.49–0.5에 7개, 0.5–0.505에 1개, 0.505–0.51에 3개, 0.51 이상에 2개가 있다. group 1 정점은 3·2·1개짜리 **세 연결요소**로 흩어져 있고, 세 정점 모두 group 1인 face는 **0개**다.

| group | vertices | vertex ratio | majority faces | face ratio | majority area ratio | components | largest component |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | 381,850 | 99.998429% | 763,670 | 99.999214% | 99.999154% | 27 | 190,568 |
| 1 | 6 | 0.001571% | 6 | 0.000786% | 0.000850% | 3 | 3 |

Face와 area는 각 triangle의 세 vertex 중 다수 group으로 배정했다. group이 섞인 face는 30개다. group 1의 다수결 face 6개도 모두 group-1 vertex 두 개와 group-0 vertex 한 개로 이뤄져 homogeneous group-1 surface는 없다. group별 좌표 범위와 상위 component bbox는 [`official_code_result.json`](official_code_result.json)에 저장했다.

GT는 fixed이고 공식 max/round 분류는 articulated이므로, **29354 표본 단위 공식 분류는 false positive다.** 이 분류 판정과 공간 분석을 구분한다. 공간적으로는 여섯 threshold-crossing vertex가 연결된 homogeneous mesh surface 영역을 이루지 않는다. 이상치가 생긴 원인은 미확정이며, 이는 전체 관절 정확도에 대한 결론이 아니다.

## scale, density, affordance 비교

예측 scale의 vertex 평균은 **99.788567 cm**다. 공식 코드가 JSON dimension vector의 최대값을 scalar GT로 만드는 규칙이 확인됐으므로 120 cm와 직접 비교할 수 있다. 절대오차는 **20.211433 cm**, 상대 절대오차는 **16.842861%**다. 이는 한 표본의 코드상 scalar 비교이며 논문 집계 결과가 아니다.

예측 density 범위는 0.681129–6.491174 g/cm³, 평균은 1.464480 g/cm³다. 예측 affordance의 학습-normalized output 범위는 0.244115–0.651860, 평균은 0.575026이다. 하지만 generated mesh vertex를 원본 여섯 part label/OBJ로 연결하는 공식 correspondence는 raw output에 없고, generated vertex의 group id는 part id가 아니다. 공식 source에서도 generated vertex→원본 part mapping을 보존하는 경로를 확인하지 못했다. 따라서 nearest-part, ICP 또는 임의 정렬을 만들지 않았고 part별 오차·PSNR도 계산하지 않았다. [`semantic_preview.png`](semantic_preview.png)는 GT part 값과 예측 분포를 나란히 둔 관찰용 그림이다.

Description은 language slice 불일치와 공식 평가 질문 미확정 때문에 제외했다.

## 공식 indexing과 수정 후보

공식 `example.py` 206행의 child threshold는 위 6개 정점을 선택한다. 이어지는 207행은 길이 381,856인 group vector를 child mask로 추린 길이 6의 parent vector와 비교하여 실제 CPU 검산에서 size mismatch가 발생했다. 211–212행의 `kinematic_map[(group_ind-1)*2]`는 column mask가 아니라 길이 2의 integer row다. 해당 표현만 독립 실행하면 `[2,8]`을 선택한다. 이 공식 경로는 완료된 kinematic 결과가 아니며 [`official_indexing_result.json`](official_indexing_result.json)에 분리했다.

기존 수정 후보인 `kinematic_map[:,(group_ind-1)*2].bool()`은 6개 정점과 `[6,8]` parameter를 선택한다. 이 후보의 평균값은 [`indexing_correction_candidate.json`](indexing_correction_candidate.json)에 별도로 저장했으며 공식 결과라고 부르지 않는다. 5-row 합성 tensor에서도 공식 표현은 첫 row의 두 integer를 index로 쓰고 후보는 의도한 boolean column을 쓰는 차이를 확인했다([`indexing_synthetic_check.json`](indexing_synthetic_check.json)). Indexing을 고치는 것만으로 관절 존재, parameter 단위나 GT 일치가 검증되지는 않는다.

## 미검증

Generated vertex와 GT part의 대응, part별 density·affordance 오차, description, movement parameter의 단위와 의미, 관절 정확도, 렌더 map·mask·camera가 필요한 PSNR, instantiation distance, 30-view 논문 평가와 전체 test 성능은 평가하지 못했다.
