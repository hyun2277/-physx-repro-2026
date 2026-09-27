# PhysX-3D 논문 동일 정량평가 readiness gate

- 판정일: 2026-09-27 (Asia/Seoul)
- 논문: [PhysX-3D v4](https://arxiv.org/html/2507.12465v4), 2025-11-28
- 고정 공식 코드: `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`
- 판정: **현재 논문과 동일한 정량평가는 실행할 수 없다.**
- 범위: 논문·공식 코드·로컬 자료·기존 29354/24566/29806 결과의 읽기 전용 대조. 추론, GPU, Blender, 설치, 다운로드, ZIP 추출, 평가 코드 구현은 수행하지 않았다.

이 판정은 모델 출력 생성 가능성과 평가 규약 완결성을 구분한다. 원본 공식 table 예제와 RTX 5090 적응 경로의 세 표본 mesh·physics 생성 성공은 확인됐지만, 논문 Table 2와 같은 test-set 점수를 만드는 입력 대응표, GT 렌더, 채점 세부식과 집계 규칙은 완결되지 않았다.

## 1. 논문이 보고하는 9개 지표

논문 v4 §5.2와 Table 2는 다음 9개 열을 보고한다.

| 영역 | 지표 | 논문에 명시된 범위 |
|---|---|---|
| Geometry/appearance | RGB PSNR ↑ | 단위 구면에서 무작위 30시점을 뽑아 평균 |
| Geometry | Chamfer Distance ↓ | 표기 `×10^-3`; 세부 표면 샘플링과 거리 구현은 미기재 |
| Geometry | F-score ↑ | threshold 0.05; 표기 `×10^-2` |
| Absolute scale | Euclidean distance ↓ | 물리 dimension에서 얻은 absolute scale 비교 |
| Material | density-map PSNR ↑ | 논문과 README는 material 열을 density PSNR로 설명 |
| Affordance | affordance-map PSNR ↑ | 렌더된 affordance map 비교 |
| Kinematics | COV ↑ | Instantiation Distance 기반 집합 지표 |
| Kinematics | MMD ↓ | Instantiation Distance 기반 집합 지표 |
| Description | cosine-similarity score-map PSNR ↑ | 질문과 CLIP description embedding으로 만든 map 비교 |

공식 README 114–130행은 scale Euclidean distance, density/affordance/description PSNR, kinematics Instantiation Distance만 안내한다. CD/F-score와 appearance PSNR의 상세 조건은 논문에만 있고, 저장소에는 9개 지표를 끝까지 계산·집계하는 evaluator가 없다.

## 2. metric별 readiness

상세 대응표는 [`2026-09-27_PhysX-3D_정량평가_readiness_gate.csv`](../../03_평가및최종보고서/평가규약/2026-09-27_PhysX-3D_정량평가_readiness_gate.csv)에 있다.

| 지표 | 공식 코드에서 확인된 입력·함수·출력 | 현재 실제 보유 | 빠진 필수 자료·규약 | 지금 실행 | 조건 판정 |
|---|---|---|---|---|---|
| RGB PSNR | `render_multiview`는 30-view Hammersley RGB와 camera를 반환하지만 공식 scorer·GT 연결 없음 | 3개 표본의 textured input과 생성 mesh, 24-view conditioning PNG/transforms | 논문 무작위 30-camera manifest, 동일 GT/pred renderer·mask·색공간·해상도·MAX·집계 | 불가 | 논문 동일 아님 |
| CD | 저장소 evaluator 없음; 설치 Kaolin 함수는 재사용 후보일 뿐 | 3개 generated mesh와 대응 원본 part/model mesh | 평가 mesh 선택, 좌표/scale 정규화, 표면점 수·면적 sampling·seed, squared 여부, 양방향 결합, 실패·집계 | 불가 | 별도 규약이면 소표본 probe 가능 |
| F-score | 저장소 evaluator 없음; 논문 threshold 0.05만 확정 | CD와 같은 mesh | CD 공통 규약, precision/recall 방향, 경계·빈 점군 처리, 집계 | 불가 | 별도 규약이면 소표본 probe 가능 |
| Scale | GT 예제는 dimension 최대값을 `scale.npy`로 저장; example은 head 역정규화 후 vertex 평균 출력 | 29354 GT 120 cm와 예측 99.788567 cm | test 1K 예측, 공식 물체/중복 평균과 실패 분모 | 논문 집계 불가 | 29354 한 건 별도 비교 가능 |
| Density PSNR | GT 예제는 part density를 정점에 넣어 30개 `.npy`; example은 density를 역정규화 후 display min-max | 3개 raw/property-head 결과와 JSON part density | generated vertex↔GT part 대응, 동일 camera/map/mask, g/cm³ 범위/MAX, GT renderer 수정, 집계 | 불가 | 분포 관찰만 가능 |
| Affordance PSNR | GT 예제는 `priority_rank`; 학습 전처리는 별도 정규화; example은 출력별 min-max display | 3개 예측과 JSON part rank | 정답 척도·방향, generated vertex↔part 대응, 동일 camera/map/mask/MAX, 집계 | 불가 | 분포 관찰만 가능 |
| Description PSNR | example은 질문 CLIP embedding과 vertex language feature cosine map; GT 예제는 무작위 part의 0/1 map | JSON description과 checkpoint는 있으나 평가 질문/score-map pair 없음 | 질문 manifest·question type·CLIP revision, GT cosine map 생성법, seed, camera/mask/MAX, 질문/뷰/물체 집계 | 불가 | 현재 직접 점수도 불가 |
| Kinematics COV | README가 NAP를 링크; 공식 PhysX→NAP 변환·scorer 없음 | 24566/29806 GT JSON과 예측 group/property 결과 | group/part matching, pose/point sampling, parent/axis/location/range 좌표·단위, NAP revision, D 방향·pool·중복·고정물체 처리 | 불가 | group 수·표면 영역 관찰만 가능 |
| Kinematics MMD | COV와 같은 Instantiation Distance matrix 필요 | COV와 동일 | COV와 동일; 완전한 generated×reference 집합 거리행렬 필수 | 불가 | 단일 표본 값으로 대체 불가 |

따라서 **9개 지표 모두 현재 자료로 논문 동일 test-set 점수를 낼 수 없다.** 이는 각 표본의 output 생성 실패를 뜻하지 않는다.

## 3. 30-view와 현재 24-view의 차이

논문은 appearance 평가에 **unit sphere의 random 30 views**와 view 평균 PSNR을 명시한다. 구체적 sampler, seed, 물체별 재표본 여부, radius, FOV, intrinsics, 해상도, 배경, mask와 색공간은 공개 문서에서 확정되지 않았다.

현재 24566·29806 등에 있는 24-view는 `dataset_toolkits/render_cond.py`의 **conditioning input 생성물**이다.

- 기본 `num_views=24`, 해상도 1024다.
- Hammersley 방향에 seed를 고정하지 않은 random offset을 더한다.
- radius/FOV도 난수로 뽑는다.
- `transforms.json`은 그 실행에서 실제 생성한 camera를 보존하지만 논문 평가 camera manifest는 아니다.

공식 `example_render_gt_foreval.py`가 `num_frames=30`을 쓰더라도, `render_video_gt`는 yaw linspace와 sinusoidal pitch, `r=2`, FOV 40°, 해상도 512인 궤도다. `render_multiview`의 30-view도 deterministic Hammersley다. 어느 쪽도 논문의 “random views from a unit sphere”와 동일하다는 근거가 없다. 숫자 30만 같다는 이유로 대체할 수 없다.

## 4. 대응 관계와 공식 코드의 실행 간극

### GT map/mask와 pixel·vertex 대응

PhysXNet ZIP의 중앙 목록은 `finaljson` 32,048개와 `partseg` member 479,807개로 구성되고, render/transforms/metric-ready mask는 포함하지 않는다. JSON과 part OBJ는 GT map의 원료지만 camera별 정답 map 자체는 아니다.

공식 GT 예제는 part OBJ 정점에 rank/density/선택-part 값을 붙여 렌더하려 하지만 현재 고정 소스에는 다음 간극이 있다.

- part loop에서 현재 `part`가 아니라 이전 `meshname`을 사용한다(`example_render_gt_foreval.py:152–169`).
- caller는 `MeshExtractResult`를 `render_video_gt`에 넘기지만 helper는 `gt[0:3]` 첨자를 요구한다(`:172–181`, `render_utils.py:117–125`).
- helper 반환 요청에는 `rendervis`가 없는데 caller는 `video['rendervis']`를 읽는다(`:181`, `:197`).

따라서 공식 파일 그대로 metric-ready density/affordance/description GT map을 생성한다고 확인할 수 없다. 예측 map과 GT map에 동일 camera·mask를 적용하는 evaluator도 없다.

Generated mesh 정점은 원본 GT part OBJ 정점과 직접 대응하지 않는다. 저장된 raw output에는 generated vertex→GT part ID가 없다. nearest-part, ICP, 임의 정렬로 대응을 만들면 별도 평가가 되므로 논문 점수에 사용할 수 없다.

### Kinematics

JSON은 group, parent, movement type, direction, position, range를 제공한다. 그러나 공개 코드에는 generated group과 GT group을 매칭하는 규칙, 좌표 변환, B/C/CB의 pose sampling, axis/location/range 단위, 고정·복수 관절 처리와 PhysX output을 NAP `.npz`의 `pcl[S,N,3]`·`pose[S,P,4,4]`로 바꾸는 규약이 없다.

NAP의 COV/MMD helper와 wrapper는 거리행렬 전치 때문에 집계 방향도 달라질 수 있다. PhysX 저자가 사용한 NAP revision, 방향, reference pool과 분모가 확인되지 않았다. COV/MMD는 집합 지표이므로 24566 또는 29806의 group count를 대신 넣을 수 없다.

### Description

논문은 질문에 대한 CLIP cosine similarity score map의 PSNR을 말한다. 공개 GT 예제는 `parts[0]['Basic_description']`을 질문으로 읽지만, 실제 GT map은 무작위 part 하나를 1로 표시하며 반복문의 각 part description을 같은 파일명으로 덮어쓴다. 공개 코드만으로 test item별 질문 문자열, basic/functional/kinematic question type, CLIP revision, target embedding/part, random seed와 집계 규칙을 복원할 수 없다.

## 5. test 1,000행과 중복 ID

논문은 24K train, 1K validation, 1K test를 명시한다. 공식 `val_test_list.npy`는 2,000행이며 README는 앞 1,000행/뒤 1,000행으로 설명한다. 로컬 실물 SHA256은 `b2cc94a8a8ae1c8f2f5ca17de35f784d4bd220723223449141bea1dfab7122fc`다.

뒤 1,000행은 고유 object ID 972개다. 중복 ID는 27개, 중복으로 늘어난 행은 28개, 최대 multiplicity는 3이다. 공식 GT 예제는 ID를 output directory key로 쓰므로 중복 행이 같은 폴더를 재사용한다. 중복이 별도 view/question인지 단순 반복인지, 행 평균인지 ID 평균인지, 실패/N/A의 분모가 무엇인지는 확인되지 않았다. 이 규칙이 없으면 논문과 같은 최종 집계를 만들 수 없다.

로컬 `finalindex.json`은 test 1,000행 중 960행을 ShapeNet에 매핑하고 40행(고유 ID 39개)은 매핑하지 않는다. 매핑된 test 행은 26개 ShapeNet synset에 걸친다. 현재 로컬 ShapeNet archive는 `04379243.zip` 하나이며 이 category에는 매핑 행 317개가 속한다. 나머지 643개 매핑 행의 25개 category archive는 로컬에 없다. 다만 이 archive들을 받는 것만으로 40개 unmapped 행이나 공식 입력/camera/GT 규약이 해결되지는 않는다.

## 6. 지금 실제로 가능한 최소 평가

아래는 **논문 정량평가가 아닌 로컬 단일/소표본 진단**이다.

1. **29354 scale scalar 비교**: 공식 코드의 GT 변환에 따라 120 cm 대 예측 vertex 평균 99.788567 cm, 절대오차 20.211433 cm(상대 절대오차 16.842861%). 한 건이며 test 집계가 아니다.
2. **29354 fixed/group 판정 관찰**: GT fixed, 공식 `num_group=2`라 표본 분류 false positive지만 group 1은 정점 6개·homogeneous triangle 0개라 의미 있는 관절 표면은 형성되지 않았다.
3. **24566 articulation 관찰**: GT 2 groups/B translation, 공식 예측 1 group으로 단일 표본 false negative다.
4. **29806 articulation/viewpoint 관찰**: GT 4 groups/C rotation 3개. 000.png는 공식 2 groups, 동일 seed 006.png probe는 3 groups지만 제2 moving group은 정점 2개뿐이다. 시점 변경 관찰이며 정량 관절 정확도가 아니다.
5. **별도 geometry probe 후보**: 세 generated mesh와 보유 GT mesh에 공개된 자체 sampling/normalization을 적용해 CD/F-score를 계산할 수는 있다. 공식 규약이 아니므로 논문 Table 2와 비교하지 않는다.

Density·affordance는 generated vertex↔GT part 공식 대응이 없어 현재는 GT part 표와 예측 분포를 나란히 보는 수준이다. Description과 Instantiation Distance는 최소 직접 점수도 낼 수 없다.

## 7. 누락 자료, 출처와 최소 확보 판정

| 항목 | 공식 출처/공개 상태 | 로컬 상태 | 필요한 최소 확보·판정 |
|---|---|---|---|
| PhysXNet JSON·part OBJ | HF `Caoza/PhysX-3D`; 공개 dataset archive | `PhysXNet.zip` 16,306,354,206 bytes 보유 | 원료는 보유. 전체 추출은 이 gate에 필요 없음 |
| test split | 고정 공식 source의 `val_test_list.npy` | 보유 | 추가 다운로드 없음; 중복 의미는 저자 확인 필요 |
| ShapeNet mesh/texture | gated HF `ShapeNet/ShapeNetCore`; 접근 승인됨 | `04379243.zip` 1,666,983,898 bytes만 보유 | 공식 1K input 생성이 필요하다고 확인된 뒤, 매핑된 나머지 25 category archive가 파일 단위 후보. 정확한 총 bytes는 이번 조사에서 재조회하지 않았고, 40행은 mapping 자체가 없음 |
| PartNet 원본 | gated HF `ShapeNet/PartNet-archive`; 접근 승인됨 | 118,428,243,304-byte split archive 미보유 | PhysXNet ZIP에 test JSON/part OBJ가 있으므로 현재 readiness blocker를 해결하기 위한 최소 다운로드로 확정하지 않음. 저자가 원본 PartNet asset을 scorer에 요구한다고 확인할 때만 필요 |
| conditioning input/camera manifest | 공식 제공 위치 미확인 | 3개 표본의 자체 24-view만 존재 | test 1,000행의 정확한 image/frame/camera/seed manifest가 필요. 공개 파일 존재 미확정 |
| metric-ready GT map/mask | 공식 제공 위치 미확인 | 없음 | 동일 camera의 RGB/density/affordance/description numeric maps와 masks 또는 이를 정확히 생성하는 수정된 공식 코드·manifest 필요 |
| geometry evaluator config | 공식 제공 위치 미확인 | 없음 | mesh 선택, normalization, surface sampling과 CD/FS config 필요 |
| kinematics evaluator package | README는 NAP 공개 repo만 링크 | PhysX adapter·ID matrix 없음 | PhysX→NAP conversion, group matching, pose sampling, 좌표/단위, revision, COV/MMD 방향/pool 필요 |
| description question/embedding manifest | 공식 제공 위치 미확인 | 없음 | test item별 question/type/CLIP model-target mapping 필요 |

현재 **추가 다운로드만으로 readiness gate를 통과할 수 없다.** 정확한 official input/evaluation package의 존재와 위치가 먼저 확인되어야 하므로, 최소 다운로드의 정확한 파일명·총량도 지금은 확정할 수 없다. PartNet 118 GB archive를 먼저 받는 것은 이 blocker에 대한 근거 있는 최소 조치가 아니다.

## 8. 저자에게 확인할 질문

논문 동일 평가에는 저자 문의가 필요하다.

1. test 1,000행 각각의 conditioning image, camera, question manifest와 중복 28행의 의미·가중치는 무엇인가?
2. random 30-view의 sampler/seed, per-object 재표본 여부, extrinsics/intrinsics, radius/FOV, 해상도, 배경, mask, 색공간은 무엇인가? 같은 camera를 RGB와 세 property map에 모두 쓰는가?
3. CD/F-score의 평가 mesh, centering/scale, 표면 point 수·sampling seed, Chamfer 식(squared 여부와 방향 결합), F-score precision/recall과 최종 집계는 무엇인가?
4. density/affordance/description map의 값 범위, normalization, PSNR MAX, mask 밖 처리, view→object→test 집계는 무엇인가? 공식 수정판 GT renderer가 있는가?
5. description의 item별 질문 문자열/type, CLIP model revision, GT cosine map과 part/embedding 대응은 무엇인가?
6. PhysX group을 NAP graph/pose로 바꾸는 방법, group matching, parent/axis/location/range 좌표·단위, pose sampling, NAP revision, COV/MMD matrix 방향·pool·고정물체 처리는 무엇인가?
7. `finalindex.json`에 없는 test 고유 ID 39개의 texture/input source와 실패·누락 표본의 공식 분모 처리는 무엇인가?

## 9. 별도 30-view probe 제안

공식 답변 전에도 24566과 29806에 대해 **자체 30-view probe**를 설계할 수 있다. 이는 제안이며 실행하지 않았다.

- 두 표본에 동일한 공개 camera 생성 코드, 고정 seed, 30개 camera matrix, intrinsics/FOV/resolution/background를 manifest로 고정한다.
- 각 camera의 원본 conditioning image hash와 동일 sampling seed/checkpoint/adapter를 기록한다.
- GT group 수와 예측 group 수, 각 예측 moving group의 vertex/face/area/components만 같은 규칙으로 비교한다.
- generated group과 GT part의 직접 대응이 없으므로 parent/axis/range 오차, density/affordance PSNR은 계산하지 않는다.
- 관찰 단위는 `(object_id, camera_id, seed)`로 두고 실패를 삭제하지 않는다. 24566과 29806을 합쳐 논문 test 성능으로 평균하지 않는다.
- 결과 제목과 표에 `self-designed 30-view viewpoint probe; not the PhysX-3D paper protocol`을 명시하고 Table 2 숫자와 비교하지 않는다.

## 10. 최종 gate

| Gate | 상태 | 근거 |
|---|---|---|
| 9개 metric 정의가 실행 수준으로 고정됨 | FAIL | 논문은 큰 틀만 명시; 공개 evaluator/config 부재 |
| official test input·question·camera 대응 | FAIL | 1K row manifest와 duplicate 의미 미확정 |
| metric-ready GT와 prediction correspondence | FAIL | map/mask 부재, vertex↔part mapping 부재, GT 예제 실행 간극 |
| geometry/kinematics 집계 규약 | FAIL | CD/FS sampling과 NAP conversion/COV-MMD 방향 미확정 |
| 전체 test prediction | FAIL | 기존 결과는 3 object 및 29806 추가 view뿐 |
| 소표본 자체 진단 | PASS | scale 1건과 group count/표면 영역 관찰 가능 |

결론은 **논문 동일 정량평가 실행 불가, 자체 소표본 진단만 가능**이다. 다음 우선순위는 (1) 저자에게 evaluator·manifest·규약을 요청하고, (2) 받은 artifact의 test ID/camera/question/hash를 로컬 split과 대조하며, (3) 그 뒤 필요한 ShapeNet category만 산정하는 순서다.
