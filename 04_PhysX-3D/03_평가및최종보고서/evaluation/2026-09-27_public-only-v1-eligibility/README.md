# 공개 자료 기반 독립 평가 v1: 10–30표본 artifact eligibility

이 조사는 새 다운로드, ZIP 추출, GPU/Blender, inference, 학습을 하지 않았다. `PhysXNet.zip` 중앙 목록, 고정 source의 `val_test_list.npy`·`finalindex.json`, 현재 `04379243.zip` 중앙 목록과 minimal 추출물, 그리고 기존 세 표본 artifact만 읽었다. 결과는 **논문 Table 2 평가나 논문 동일 평가가 아니다.**

## 상태 정의와 우선순위

행은 official test 마지막 1,000행의 순서와 duplicate occurrence를 그대로 보존한다. 하나의 행에 여러 문제가 있어도 다음 우선순위로 하나의 상태만 부여한다: `SOURCE_MISSING` → `MAPPING_UNRESOLVED` → `NEEDS_SHAPENET_FILE` → `NEEDS_CONDITIONING` → `COMPLETE_NOW` 또는 inference memory 상태.

- `COMPLETE_NOW`: JSON/part OBJ/part PNG, ShapeNet OBJ+MTL+texture, conditioning, generated mesh/raw physics/property artifact가 모두 실제 file hash로 확인됨.
- `READY_FOR_INFERENCE`: GT·texture·conditioning은 있으나 generated artifact가 없고, 비교 가능한 memory evidence가 있음.
- `NEEDS_SHAPENET_FILE`: finalindex mapping은 있으나 현 raw ZIP/minimal에 mapped OBJ+MTL+texture가 없음.
- `NEEDS_CONDITIONING`: GT와 texture는 현재 확인됐지만 conditioning transforms가 없음.
- `MAPPING_UNRESOLVED`: finalindex mapping이 없음.
- `SOURCE_MISSING`: PhysXNet ZIP에 JSON, part OBJ, part PNG 중 하나 이상이 없음.
- `UNSAFE_OR_UNKNOWN_MEMORY`: inference 직전까지 원료가 있지만 comparable sampling/decoder memory evidence가 없음.

이번 census에서는 READY/UNSAFE 상태까지 도달한 신규 행이 없었다. texture가 현재 있더라도 conditioning이 먼저 없으므로 `NEEDS_CONDITIONING`으로 기록된다.

## census 결과

| 상태 | 행 수 | 의미 |
|---|---:|---|
| COMPLETE_NOW | 3 | 29354, 24566, 29806. 기존 v1 독립 평가에 바로 포함 가능 |
| NEEDS_CONDITIONING | 243 | `04379243.zip` 중앙 목록에서 mapped OBJ/MTL/texture를 확인했으나 conditioning artifact 없음 |
| NEEDS_SHAPENET_FILE | 713 | mapping은 있으나 현 04379243 raw/minimal 외 category가 필요 |
| MAPPING_UNRESOLVED | 40 | finalindex mapping 없음 |
| SOURCE_MISSING | 1 | test index 971, object 36610: ZIP 원료 완결성 불충족 |

`validation_result.json`은 1,000행 순서, duplicate occurrence, status code, COMPLETE_NOW hash, required category alignment를 CPU에서 검증한 결과다.

## 현재 즉시 가능 범위

현재 즉시 가능한 독립 평가 v1 표본은 **29354, 24566, 29806의 3개**다. 세 표본은 각각 fixed, B translation, C rotation 계층을 하나씩 포함하지만, 이 수로 10–30표본 확장이나 논문 성능 일반화를 할 수 없다.

## 10개 신규 제안과 최소 확보 경로

`proposal_10_new_samples.csv`는 완료된 세 표본을 다시 세지 않고 fixed 4, B 3, C 3을 우선순위로 제안한다.

- 현재 texture 원료가 이미 있는 conditioning 우선 후보: 21356, 27703, 30719, 21314 (fixed), 27281 (B+C), 23787 (C). 이 6개는 새로운 ShapeNet ZIP 없이도 다음 단계의 conditioning 준비가 필요하다.
- 추가 ShapeNet ZIP이 필요한 proposal 후보: 48419·38882는 `02933112.zip`, 14567·15821은 `03636649.zip`이 필요하다. 이 두 ZIP의 metadata size는 이번 작업에서 새 API 조회를 하지 않았으므로 **unknown**이다.

`required_files.csv`에는 finalindex가 매핑한 category 26개를 모두 적고, category마다 연결된 test row 수와 object ID를 보존했다. 현재 보유 `04379243.zip`의 확인된 size는 1,666,983,898 bytes이고, 나머지 25 category ZIP의 크기는 이 조사에서 확인하지 않아 추정하지 않았다. ZIP 하나를 확보해도 해당 행은 texture 단계만 해소되며 conditioning·generated artifact는 별도 상태로 남는다.

## PartNet 필요성

이번 공개 자료 기반 독립 평가 v1의 eligibility 단계에는 **PartNet archive가 필요하지 않다.** 현 PhysXNet ZIP 중앙 목록에서 test JSON, part OBJ, part PNG를 직접 확인했기 때문이다. PartNet 원본은 저자가 별도 scorer 또는 provenance에 요구한다고 확인될 때만 다시 검토한다. 이 판단은 논문 동일 평가에 필요한 자료가 모두 있다는 뜻이 아니다.

## 확장 판단

CPU manifest/evaluator는 eligible artifact가 10–30개로 늘면 확장할 수 있다. 실제 10개 확장은 아직 불가능하다. 6개에는 conditioning와 generated outputs가, 4개에는 위 category ZIP과 그 뒤 conditioning/generated outputs가 추가로 필요하다. 40개 mapping-unresolved 행과 source-missing 행은 파일 확보만으로 해결된다고 가정하지 않는다.
