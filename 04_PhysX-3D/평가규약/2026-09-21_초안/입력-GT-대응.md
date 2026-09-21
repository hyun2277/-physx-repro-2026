# PhysX-3D 평가 입력·GT 대응표

작성일: 2026-09-21. **배포 설명과 코드에서 유도한 대응 초안이다. 실제 데이터 파일의 대응 검증은 아직 하지 않았다.** 데이터·모델을 다운로드하거나 전처리·추론·평가를 실행하지 않았다. 분류는 [평가 규약](평가규약.md)의 `[저자] / [코드] / [제안] / [미확정]`을 따른다. 고정 소스와 행 번호는 [근거목록](근거목록.md)을 참조한다.

## 1. 공식 정답 자료의 제공 위치

| 자료 | 공개 위치·확인 범위 | 아직 확인하지 않은 부분 |
|---|---|---|
| PhysXNet 원시 annotation·부품·입력 이미지 | [공식 HF 데이터 저장소](https://huggingface.co/datasets/Caoza/PhysX-3D/tree/ca1f6d3f5cfb5c39dc183251a3a2999dcb42e093)의 `PhysXNet.zip`. [공식 설명](https://huggingface.co/datasets/Caoza/PhysX-3D/blob/ca1f6d3f5cfb5c39dc183251a3a2999dcb42e093/README.md)은 `finaljson/<id>.json`, `partseg/<id>/img/*.png`, `partseg/<id>/objs/*.obj` 구조를 안내 | archive 내부를 열지 않았으므로 각 파일의 존재·개수·카메라 metadata·완성된 평가용 GT 맵 포함 여부는 미확인 |
| 원래 test 목록 | [공식 `val_test_list.npy`](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/val_test_list.npy), 로컬 원본과 기존 조사 재사용. README는 앞 1,000 validation / 뒤 1,000 test라고 설명 | 중복 ID가 생긴 이유와 최종 집계 단위는 미확정 |
| texture를 연결할 ShapeNet 자료 | 공식 PhysX README가 [ShapeNetCore](https://huggingface.co/datasets/ShapeNet/ShapeNetCore)와 [PartNet archive](https://huggingface.co/datasets/ShapeNet/PartNet-archive)를 연결. 로컬 `dataset_toolkits/finalindex.json`은 대응 경로 자료 | 해당 object/part와 실제 texture 파일의 일치·누락·정합은 미검증. 경로 JSON의 존재는 textured GT 확보를 뜻하지 않음 |
| 렌더된 숫자 GT 맵·관절 pose | 공식 README의 GT 생성 코드 `example_render_gt_foreval.py`가 로컬 생성 경로를 제시 | 조회한 HF 파일 목록에서는 별도 평가 GT 맵 파일을 찾지 못함. archive 내부에도 없다는 뜻은 아님. GT 생성 코드의 정적 연결 문제도 남아 있음 |

HF 조회 revision은 `ca1f6d3f5cfb5c39dc183251a3a2999dcb42e093`이다. `PhysXNet.zip` 메타데이터 크기는 **16,306,354,206 bytes (16.31 GB / 15.19 GiB)**, LFS SHA256은 `a4970a3936e8a1fc823d17b64d23b167d73997a13686011bc46f7b98774a7e75`이다. 이는 [공식 API 메타데이터](https://huggingface.co/api/datasets/Caoza/PhysX-3D/revision/ca1f6d3f5cfb5c39dc183251a3a2999dcb42e093?blobs=true)에서 읽은 값이며, 다운로드한 파일을 검증한 결과가 아니다. XL 자료를 기본 PhysXNet/test의 대체물로 선택하지 않았다.

**로컬 경로 차이:** README의 해제 대상은 `dataset_toolkits/physxnet`이지만, GT 예제는 실행 디렉터리 기준 `./PhysXNet/finaljson`·`./PhysXNet/partseg`를 기대한다. 같은 경로라고 가정하지 않는다. 향후 데이터 root를 명시적으로 연결해야 하며, 이번에는 폴더 생성·심볼릭 링크·다운로드·경로 패치를 하지 않았다. 기존 조사에서 지정 프로젝트 경로의 GT 자료는 미확보 상태다. 다른 사용자 환경을 검색한 결과는 아니다.

## 2. 원본 순서를 보존한 test 대응표

[test-input-gt-correspondence.csv](test-input-gt-correspondence.csv)는 원본 **뒤 1,000행을 그대로 보존한 부분 작성 대응표**다. 원본 NPY는 변경하지 않았고, 정렬·중복 제거·새 split을 만들지 않았다. ID와 행 번호, 코드에서 유도한 후보 GT 경로만 채웠다. 실제 입력·질문·카메라·GT 파일 확인은 완료되지 않았다.

- 원본 NPY: 40,128 bytes, 2,000항목, dtype `<U5`.
- 원본 SHA256: `b2cc94a8a8ae1c8f2f5ca17de35f784d4bd220723223449141bea1dfab7122fc`.
- test: 1,000행 / 고유 ID 972개. 한 번 등장 945개 ID, 두 번 등장 26개 ID, 세 번 등장 1개 ID. 중복 ID 27개, 중복으로 추가된 행 28개.
- `test_index_0based`: 0–999, `source_index_0based`: 1000–1999. **행 번호는 0부터** 시작한다.
- 기존 NPY를 표준 라이브러리로 읽어 문서 CSV를 작성하고 순서·개수를 대조했다. 모델이나 수치 평가 라이브러리를 실행한 것이 아니다.

| CSV 열 | 의미·현재 값 |
|---|---|
| `test_index_0based`, `source_index_0based`, `object_id` | 원본 순서·ID. ID는 문자열이며, 스프레드시트에서 숫자로 변환하지 않는다 |
| `same_id_occurrence_1based` | test 원래 순서에서 같은 ID의 몇 번째 등장인지. 별도 뷰/질문이라는 의미나 집계 가중치가 아님 |
| `gt_json_candidate_relative` | `finaljson/<id>.json`; 배포 설명·코드에서 유도한 상대경로 후보 |
| `gt_parts_candidate_relative` | `partseg/<id>/objs/`; 동일한 후보. 파일이 있다는 확인이 아님 |
| `gt_paths_verified` | 전부 `false` |
| `input_image_path`, `input_view_id`, `input_camera_hash` | 미확정이므로 빈칸 |
| `question_type`, `question_part_id`, `question_text`, `eval_camera_set_id` | 미확정이므로 빈칸. 빈칸은 N/A 또는 질문 없음의 확정값이 아님 |
| `duplicate_aggregation_policy` | 전부 `UNRESOLVED`; 행 평균/ID 평균을 결정하지 않음 |
| `mapping_status` | 전부 `GT_NOT_AVAILABLE`; 경로·대응 검증 완료를 표시하지 않음 |

**[제안]** 향후 출력 저장 키는 원본 행 번호와 ID를 함께 포함한다. 동일 ID의 출력 덮어쓰기를 막기 위한 조치이며, 중복 행을 독립 표본으로 가중하겠다는 결정은 아니다. 평가 대응 파일을 확장할 때 이 CSV와 원본은 보존하고, 확장본의 revision/hash 및 부모 대응표 hash를 남긴다.

## 3. 입력 → 물체 → 부품 → 질문 → 뷰 연결

| 연결 | 저자 설명·코드에서 확인한 부분 | 연결 전 해결할 부분 |
|---|---|---|
| test 행 → object ID | 뒤 1,000항목과 원래 순서를 사용 | 중복 행의 의미·가중치, 누락 시 공식 분모 |
| object ID → 입력 이미지 | 배포 설명은 `partseg/<id>/img/<n>.png`. 생성 코드는 `renders_cond/<instance>/<nnn>.png` 사용 | 어느 입력 계열·몇 번 뷰가 논문 평가 입력인지 미확정. 해상도·crop·alpha 처리도 별도 확인 |
| object ID → 처리용 instance | `gen_csv.py:15–24`가 `<id>_`를 `sha256` 열에 기록하고 `phy_dataset/<id>/model_tex.obj`를 연결 | 이 `sha256` 열은 실제 파일 SHA256이 아니다. 원본 ID·처리용 ID·파일 hash를 별도 보존 |
| object ID → JSON·부품 메시 | `merge_property.py:81–93`은 `finaljson/<id>.json`, `partseg/<id>/objs/`를 사용하고 숫자 파일명으로 정렬 | JSON·OBJ 양쪽 존재, 부품 수·좌표계·texture 연결 실물 검증 필요 |
| mesh → JSON part → group | `merge_property.py:93–148`은 정렬된 mesh의 배열 인덱스를 `parts[]` 및 group child 목록 대응에 사용 | mesh 숫자 stem·`parts[].label`·배열 인덱스가 항상 같은지 미확인. 이 세 값을 각각 기록하고 검증 전 동일시 금지 |
| 부품 → 물성 정답 | 코드상 최대 dimension, density 수치, priority_rank를 읽음 | cm·g/cm³·rank의 유효 범위·누락값, 예측값과 공통 정규화·마스크·PSNR MAX 확정 필요 |
| 부품 → 설명 질문 | `merge_property.py:151–156`은 Basic/Functional/Movement 설명을 CLIP에 입력. 실제 저장은 4슬롯이며 마지막 두 슬롯은 같은 Movement embedding | 논문은 3종 설명. 코드의 네 번째 슬롯을 Grasped 등의 독립 질문으로 추정하지 않음. 예제에서 명시한 question_type은 0/1/2이고, 평가 질문 유형·대상 부품·문자열은 미확정 |
| 질문 → GT description 맵 | GT 코드는 선택한 part의 0/1 값을 렌더하려는 구조 | 첫 부품에서 정한 질문과 루프 내 재추첨 대상이 불일치할 수 있음. 논문의 cosine score map과 이 0/1 GT 정의의 일치도 미확정 |
| 입력 뷰 → 카메라 | Blender 생성기는 `transforms.json`에 파일 경로·FOV·카메라 행렬·scale/offset을 저장 | 배포 `img`에도 같은 metadata가 있는지 미확인. 입력 뷰와 평가 렌더 뷰를 구분해야 함 |
| 예측/GT → 평가 뷰 | 예제 함수는 동일한 수식의 orbit을 구성할 수 있음 | 동일 좌표계·카메라·frame 매칭이 실제로 성립하는지 검증 필요. 외관은 논문의 무작위 30시점으로 별도 규약 필요 |
| 부품 → 관절 | group의 child 목록·parent·type·axis/location/range를 읽음 | 전체 graph, root/fixed, single/multi joint, CB/D/A 처리를 보완·검증해야 함. group1 B/C 예제만으로 전체 지원 아님 |

### 카메라 계열은 서로 대체하지 않는다

1. 배포 이미지 `partseg/<id>/img`: 공식 설명에 경로만 있으며 평가용 선택 기준·카메라 대응은 미확정.
2. 조건 영상 `renders_cond`: 코드 기본 24뷰/1024px, offset·radius·FOV 무작위. 학습용 기본값을 평가 규약으로 채택하지 않음.
3. 일반 `renders`: 코드 기본 150뷰/512px, r=2/FOV=40°, offset 무작위. 학습 로더는 여기도 무작위로 선택할 수 있음.
4. 예제/GT 회전 영상: 30프레임 orbit. 입력 이미지와 일치하는 카메라라는 뜻이 아니며 논문 무작위 30시점과 다름.
5. 평가 카메라: **[저자]** 외관은 무작위 단위구 30시점. **[미확정]** 정확한 sampler·seed·intrinsic·mask 등. **[제안]** 예측과 GT가 같은 camera-set ID 및 동일 행렬을 참조하도록 저장.

학습 로더의 `camera_angle_x`, 카메라 y/z축 반전, alpha·LANCZOS resize 처리는 재사용 후보의 코드 사실이다. 평가 카메라 convention과 전처리의 확정값으로 자동 채택하지 않는다. 실패 시 무작위 다른 샘플을 뽑는 학습용 로직도 test에 옮기지 않는다.

## 4. GT 코드의 정적 차단 사항

- 질문은 첫 부품에서 읽고, description 대상 부품은 반복문 안에서 매번 재추첨하며 `des_index.npy`를 덮어쓴다. `meshname`도 현재 part에 맞게 갱신되지 않는 경로가 있다. 기존 검토 패치02/03은 현재 실행본 GT에 적용되지 않았으며 seed·질문 대응·실제 부품 순서를 모두 검증한 것도 아니다.
- GT caller는 `MeshExtractResult`를 `render_video_gt()`에 전달하지만, helper는 `gt[0]`, `gt[1]`, `gt[2]` 배열 묶음을 기대한다. caller가 요구하는 `rendervis`도 helper의 반환 요청에 없다. **정적 API 불일치이며 이번에 실행 실패를 재현한 것은 아니다.** 기존 두 패치만으로 해결되지 않는다.
- 현재 GT 예제는 목록 2,000항목 전체를 순회하고 ID만으로 출력 폴더를 만든다. test 전용 범위·중복/재시도 출력 보존이 연결되지 않았다.
- group1 B/C에서 4개 위치를 내보내는 GT 시각화와 NAP의 pose sampling은 서로 다른 경로다. 논문의 pose 수·샘플링·range 단위를 확정한 근거로 쓸 수 없다.

## 5. 향후 완성할 대응 레코드 — 제안, 아직 미구현

| 묶음 | 보존할 필드 |
|---|---|
| 출처/목록 | dataset revision, archive 기대 hash/실측 hash 구분, 원본 split hash, 원본 행 번호, object ID, occurrence, 중복 정책 상태 |
| 입력 | 입력 계열·경로·실제 hash·크기, instance ID, 입력 view ID, 전처리 설정 hash |
| geometry/part | JSON 경로/hash, part label, parts 배열 위치, mesh 파일명/hash, texture 경로/hash, 적용 축·중심·scale 변환 및 역변환 |
| 질문 | question_type/field, 정확한 text 및 hash, 목표 part label/mesh, CLIP 모델 revision·tokenizer/preprocess 식별자, GT score-map 정의 |
| 카메라/맵 | 평가 camera-set ID/hash, frame ID, extrinsic/intrinsic, camera convention, 해상도/배경/색공간/mask, 숫자 channel·단위·data range |
| 관절 | child part labels, parent, type, axis/origin/range/단위, joint graph, pose sample IDs/seed, 좌표 변환 |
| 계산/상태 | prediction/run ID, code/patch/metric config hash, sampling IDs, 원시 점수/표시 점수, 상태·실패 사유·실제 분모 |

아직 모르는 필드는 null/미확정으로 보존하고, 실제 파일 검증 전에는 경로 후보를 검증 완료로 승격하지 않는다. 우선 확인할 것은 **공식 평가 입력 뷰·질문과 중복 ID의 의미**, 그다음 **실제 JSON/부품/texture/카메라 연결**이다. 공개 자료로 해소되지 않은 조건은 [평가 규약의 차단 목록](평가규약.md#6-실행-전에-풀어야-할-차단-사항)에 따라 남긴다.
