# 생성 결과 기반 관절 명세 감사

## 범위와 동결 기준

- 감사 기준 commit: `dc62c7df196a64840344b000a54c0ba109cfa371`.
- 2026-09-29 확인 시 local `HEAD`, `origin/main`, 원격 `main`은 모두 위 commit을 가리킨다. 따라서 기준 commit은 현재 main과 동일하다.
- 대상은 기존 생성 결과 10163, 29806의 frame `006`, 29354뿐이다. GPU 추론, Blender/Isaac Sim 실행, 다운로드, 재생성은 하지 않았다.
- GT JSON은 대조만 했다. 아래 예측 필드의 빈칸을 GT의 parent·type·axis·origin·range로 채우지 않았다.

## 결론

| 사례 | 기존 생성 결과의 group | 관절 명세 판정 | 이유 |
| --- | --- | --- | --- |
| 10163 노트북 | 공식 식으로 2 groups; group 1은 5 vertices | `INTERPRETATION_BLOCKED` | raw parent/type/8개 movement 값은 있으나 parent 해석, 좌표계, 단위, 8채널 배치의 공개 규약이 없다. |
| 29806 수납장 frame 006 | 공식 식으로 3 groups; group 1은 37,408 vertices, group 2는 2 vertices | `INTERPRETATION_BLOCKED` | 동일하게 parent·좌표계·단위 해석이 막혀 있다. group 2는 의미 있는 별도 표면도 아니다. |
| 29354 고정 대조 | 공식 식으로 2 groups; group 1은 6 vertices, homogeneous triangle 0 | `NO_DEPLOYABLE_JOINT_SPEC` | 저장된 결과에는 raw 32채널과 group 감사만 있고, 14채널 property head 결과가 보존되어 있지 않다. 또한 GT fixed와 달리 공식 식은 극소수 group 1 때문에 articulated로 분기한다. |

`DEPLOYABLE_SPEC_AVAILABLE`은 parent, joint type, axis, origin, lower/upper limit을 GT·수동 보정 없이 모두 작성할 수 있을 때만 허용한다. 세 사례는 그 기준을 충족하지 않는다.

## 읽기 전용 artifact 확인

| 사례 | mesh / raw physics / property 또는 group audit | 구조 확인 |
| --- | --- | --- |
| 10163 | `staging/public-only-v1-extension-decoder-10163-20260927T155248Z-da944aafa535/mesh/mesh.obj`; `mesh/mesh_physics_raw.pt`; `articulation_audit/vertex_physics_14ch.pt`; `articulation_audit/official_result.json` | mesh 30,682,700 bytes; raw 80,282,295 bytes; 14-channel tensor `[378684,14]`, FP32, finite; raw output은 32 channels로 기록됨. |
| 29806 frame 006 | `staging/29806-viewpoint-probe-20260927T061911Z-4b32fcccb880/frame_006/mesh/mesh.obj`; `mesh/mesh_physics_raw.pt`; `articulation_audit/vertex_physics_14ch.pt`; `articulation_audit/official_result.json` | mesh 16,003,942 bytes; raw 42,835,063 bytes; 14-channel tensor `[202042,14]`, FP32, finite; raw output은 32 channels로 기록됨. |
| 29354 | `staging/rtx5090-cached-decoder-29354-20260926T194524Z-d69f74359b60/mesh.obj`; `mesh_physics_raw.pt`; `01_재현실행/자료확보/rtx5090_adapter/2026-09-27_29354-semantic-validation/official_code_result.json` | mesh 30,788,505 bytes; raw 80,955,063 bytes; decoder 기록상 vertex physics `[381856,32]`; 이 범위에는 저장된 14-channel property tensor가 없다. |

각 artifact의 절대 경로·bytes·SHA256은 [joint_field_matrix.csv](joint_field_matrix.csv)의 `artifact` 행에 보존한다. 두 14-channel tensor의 channel 순서는 기존 CPU 감사에서 `scale_cm`, `affordance`, `density_g_cm3`, `group_id`, `parent_group_id`, `movement_parameters_8`, `movement_type`로 확인했다.

## 공식 출력 경로와 해석 한계

공식 `example.py`는 `slat_decoder_output`에 raw 32채널의 마지막 16채널을 입력하고(`example.py:179`), `phy`의 0/2/4/마지막 channel에만 명시적 수치 변환을 적용한다(`:182-185`). group 수는 `round(max(phy[...,3])) + 1`이다(`:194`). group mask는 `phy[...,3]`의 반 단위 범위를 사용한다(`:204-206`). movement parameter와 type은 이 mask의 평균으로만 얻는다(`:211-212`). type 출력의 정수 해석은 `D/C/B/A/rigid` 순서로 출력된다(`:270-280`).

그러나 세 관절 후보의 기존 공식 감사는 parent mask 식(`example.py:207`)에서 전체 vertex 길이와 child mask 길이가 달라지는 shape mismatch를 기록했다. 그러므로 `phy[...,4]`의 연속값을 parent group으로 확정할 수 없다. `phy[...,5:-1]`의 8개 값은 예제에서 axis·position·range처럼 사용하려는 흔적이 있어도, 좌표 frame·단위·정규화 역변환이 공개 코드로 확인되지 않았다. 이 값들을 URDF/USD로 변환하지 않았다.

| field | 10163 | 29806 frame 006 | 29354 |
| --- | --- | --- | --- |
| part/group | `DERIVED_BY_FIXED_RULE`: group 0/1 vertex partition | `DERIVED_BY_FIXED_RULE`: group 0/1/2 vertex partition | `DERIVED_BY_FIXED_RULE`: group 0/1 vertex partition |
| parent | `INTERPRETATION_UNKNOWN`: raw channel 4 존재, 공식 parent mask 오류 | `INTERPRETATION_UNKNOWN`: raw channel 4 존재, 공식 parent mask 오류 | `MISSING_FROM_OUTPUT`: 저장된 14-channel head 결과 없음 |
| joint type | `DERIVED_BY_FIXED_RULE`: group 1 mean type 0.8596 → round 1 (`D`) | `DERIVED_BY_FIXED_RULE`: group 1/2 means 0.0595/0.0164 → round 0 (example의 rigid fallback) | `MISSING_FROM_OUTPUT` |
| axis, origin, lower/upper | `INTERPRETATION_UNKNOWN`: raw 8-vector는 존재하나 frame/unit/배치 규약 미확정 | `INTERPRETATION_UNKNOWN`: 동일 | `MISSING_FROM_OUTPUT` |
| coordinate frame, units | `INTERPRETATION_UNKNOWN` | `INTERPRETATION_UNKNOWN` | `INTERPRETATION_UNKNOWN`: mesh 좌표와 raw physics의 물리 좌표계 연결 규약 미확정 |

세 사례의 값·키·근거는 [joint_field_matrix.csv](joint_field_matrix.csv)에 field별로 분리했다. `AVAILABLE_FROM_PREDICTION`은 원시 tensor가 있다는 사실만 뜻하며, 본 감사에서는 실행 가능한 joint field에 적용되지 않았다.

## GT 전용 `urdf_gen.py` 대조

공식 `urdf_gen.py`는 generated mesh/property output을 입력으로 받는 자동 변환기가 아니다.

- dataset root를 `./physxnet`으로 고정하고 `finaljson`, `partseg`를 설정한다(`urdf_gen.py:29-35`).
- 각 object의 `finaljson/<id>.json`을 읽고 `jsondata['group_info']`를 URDF 구조의 원천으로 사용한다(`:39-45`).
- visual mesh도 `partseg/<id>/objs/<part>.obj` GT 부품 경로에서 읽는다(`:58-62`, `:79-83`, `:98-102`).
- B/C type, parent, axis, position, limit은 모두 `mov` 즉 GT `group_info`의 원소에서 꺼낸다(`:109-160`). C의 limit에는 GT range에 `pi`를 곱한다(`:160`).

따라서 이 파일은 **GT 대조군용 도구**다. 10163·29806·29354의 generated output에 직접 적용할 수 없으며, 이 감사에서 URDF/USD나 Isaac smoke test를 만들지 않은 이유이기도 하다.

## GT와의 분리

10163 GT는 fixed base + C rotation 1개, 29806 GT는 fixed base + C rotation 3개, 29354 GT는 fixed다. 이 정보는 예측 결과의 정확도를 대조하는 데만 사용했다. 예측군에 parent, type, axis, origin, range를 추가하는 데 사용하지 않았다. generated group과 GT part의 직접 대응도 확인되지 않았으므로, parent·axis·origin·range 정확도는 평가하지 않는다.

## 재개 조건

generated-output만으로 deployable spec을 만들려면 최소한 (1) property head의 8개 movement parameter channel layout, (2) normalized 값의 좌표 frame·단위·역변환, (3) parent group의 올바른 discrete assignment, (4) generated group과 link mesh를 정하는 공개 contract가 필요하다. 이 중 하나라도 GT 또는 수동 보정으로 메우면 `MANUAL_CORRECTION` 또는 `GT_ONLY`로 남기며, generated-only asset이라고 부르지 않는다.
