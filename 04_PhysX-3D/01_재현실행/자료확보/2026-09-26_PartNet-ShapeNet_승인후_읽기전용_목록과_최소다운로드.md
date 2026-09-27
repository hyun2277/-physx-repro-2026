# PartNet-archive·ShapeNetCore 승인 후 읽기 전용 조사

- 조사일: 2026-09-26 (Asia/Seoul)
- 범위: 파일 목록·원격 메타데이터·샘플 매핑 확인만 수행
- 금지 작업 준수: 다운로드, 압축 해제, 전처리, 추론, 전체 평가를 수행하지 않음
- PhysX-3D 고정 source HEAD: `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`

## 접근 확인

`envs/physxgen/bin/hf auth whoami`가 `hyun2277`을 반환했다. 같은 인증 세션에서 다음 두 gated dataset의 `repo_info` 및 recursive tree 메타데이터 조회가 성공했다.

- [ShapeNet/PartNet-archive](https://huggingface.co/datasets/ShapeNet/PartNet-archive), revision `18b21e20312c89917d765b8572eda2079f82bb7b`
- [ShapeNet/ShapeNetCore](https://huggingface.co/datasets/ShapeNet/ShapeNetCore), revision `73b692a98ee796df2f64511e0cbd4a8af2c20b27`

이는 계정이 저장소 목록·파일 메타데이터를 읽을 수 있다는 뜻이다. 파일 본문을 resolve/download하거나 압축을 열어 보지는 않았으므로, 개별 내부 파일의 실제 내용·무결성·추출 결과는 아직 확인하지 않았다. 두 데이터셋 페이지의 `other` 라이선스와 비상업 연구·교육 조건을 계속 적용한다.

## 원격 파일 목록과 구조

### PartNet-archive

API tree가 공개한 파일은 다음과 같다. `data_v0_chunk.zip`과 `.z01`–`.z10`은 하나의 분할 ZIP 세트로 보존되어야 하며, 표본 하나를 찾기 위한 내부 경로는 이 읽기 전용 조사에서 열지 않았다.

| 원격 파일 | 크기(bytes) | 용도/판정 |
|---|---:|---|
| `data_v0_chunk.zip` | 316,642,742 | PartNet v0 분할 ZIP 본체 |
| `data_v0_chunk.z01`–`.z09` | 각 10,737,418,240 | 위 분할 세트의 연속 조각 |
| `data_v0_chunk.z10` | 10,737,418,162 | 위 분할 세트의 마지막 조각 |
| `ins_seg_h5.zip` | 21,239,522,912 | 인스턴스 segmentation HDF5 보조 아카이브; 이번 두 표본의 원본 mesh 확보에 필수인지 미확정 |
| `sem_seg_h5.zip` | 8,569,950,650 | semantic segmentation HDF5 보조 아카이브; 이번 두 표본의 원본 mesh 확보에 필수인지 미확정 |
| `README.md` | 5,244 | 저장소 설명 |

`data_v0_chunk.*` 세트의 합계는 **118,428,243,304 bytes** (약 110.295 GiB)다. HDF5 두 아카이브까지 모두 받는 전체 합계는 **148,237,716,866 bytes**이나, 두 PhysXNet 표본의 원본 mesh를 찾는 최소 다운로드로 간주하지 않는다. 분할 ZIP 내부의 7271/29354 레코드 경로, 압축 해제 용량, PartNet 원본 ID는 본문을 받지 않고는 미확정이다.

### ShapeNetCore

API tree는 synset별 ZIP 55개와 문서 3개를 공개했다. 이번 후보에 직접 해당하는 원격 아카이브는 다음 하나다.

| 원격 파일 | 크기(bytes) | 용도/판정 |
|---|---:|---|
| `04379243.zip` | **1,666,983,898** (약 1.5525 GiB) | `29354`의 로컬 `finalindex.json` 후보 `shapenet/04379243/db406d9b2a94bce5622d7484764b58f`를 찾기 위한 synset 아카이브 |
| `02691156.zip` 등 나머지 synset ZIP 54개 | API tree에서 각 파일명·크기 확인 | 두 표본에 필요한 근거가 없어 최소 목록에서 제외 |
| `DATA.md`, `README.md` | 각각 2,581 / 4,250 | 저장소 설명 |

ShapeNet ZIP 내부의 `db406d9b2a94bce5622d7484764b58f` 디렉터리와 `models/model_normalized.obj`, `.mtl`, `images/*`의 실제 존재·크기는 압축을 열지 않아 미확정이다. 따라서 1,666,983,898 bytes는 후보 **아카이브 전체** 크기이며, 표본 파일만의 용량으로 축소해 추정하지 않는다.

## 표본별 최소 확보 후보

PhysXNet 공개 ZIP에서 이미 확인한 최소 표본 원료는 다음과 같다. 이는 새 다운로드가 아니라 기존 로컬 archive 조사 기록이다.

- `7271`: `version_1/finaljson/7271.json`, `version_1/partseg/7271/objs/0..5.obj`, `version_1/partseg/7271/imgs/*.png` (13 members, 1,643,252 bytes). `finalindex.json`에 ShapeNet 매핑이 **없다**.
- `29354`: 동일한 13-member 경로 집합 (744,852 bytes). 로컬 `finalindex.json`에 `shapenet/04379243/db406d9b2a94bce5622d7484764b58f` 문자열이 있다. 이는 원격 파일의 존재를 보증하지 않는 후보 식별자다.

| 표본 | 원본 PartNet 최소 파일 | ShapeNet mesh/texture 후보 | 현재 판정 |
|---|---|---|---|
| 7271 | PartNet `data_v0_chunk.zip` + `.z01`–`.z10` 분할 세트에서 해당 PartNet 레코드를 찾아야 함. 정확한 내부 경로·PartNet ID 미확정 | 매핑 없음. 임의 synset/model을 선택하지 않음 | 최소 ShapeNet 파일 목록과 용량을 정할 수 없음 |
| 29354 | 같은 PartNet 분할 세트에서 해당 레코드를 찾아야 함. 정확한 내부 경로·PartNet ID 미확정 | `04379243.zip` 안의 model hash `db406d9b2a94bce5622d7484764b58f`; 예상 파일명은 코드 후보에 `models/model_normalized.obj`가 있으나 내부 존재·texture 동반 파일은 미확정 | synset ZIP 1개가 현재 확인 가능한 최소 후보 |

PartNet 분할 세트는 표본 하나만 골라 받는 개별 파일 목록을 API가 제공하지 않는다. 따라서 **현재 실제로 필요한 최소 다운로드 단위**는 7271/29354 모두 `data_v0_chunk.zip` 및 `.z01`–`.z10` 전부이며, 표본 내부 파일명과 추출 공간은 미확정이다. ShapeNet은 29354에 한해 `04379243.zip`이 최소 후보이고, 7271은 매핑이 해결될 때까지 다운로드 후보가 없다.

압축 해제 예상 공간은 두 gated archive의 내부 압축률을 읽지 않았으므로 수치화하지 않는다. 확인 가능한 바이트 합계는 PartNet 분할 세트 118,428,243,304 bytes와 29354 후보 ShapeNet synset ZIP 1,666,983,898 bytes이며, 두 후보를 모두 받는 전송 합계는 **120,095,227,202 bytes**다. 이는 추출 후 공간이 아니다.

## 논문 동일 정량평가 자료의 완결성

PartNet-archive와 ShapeNetCore만으로는 논문 test 평가 입력을 완성할 수 없다.

- PhysXNet의 conditioning 입력 image는 ZIP의 `partseg/.../imgs/*.png`가 공식 test camera conditioning인지 연결하는 manifest가 없다. 전처리 코드가 요구하는 `renders_cond/<instance>/...`와 camera `transforms.json`은 파생 산출물이다.
- camera/transforms의 공식 test view 집합, 좌표계, intrinsics/extrinsics는 두 원본 데이터셋에 포함된 것으로 확인되지 않았다.
- metric-ready GT map/mask(재질·affordance·description의 렌더 map과 평가용 mask), 질문-관절 대응 및 kinematic GT manifest는 PartNet/ShapeNet 원본 archive만으로 제공된다고 확인할 수 없다. PhysXNet annotation JSON은 물성/부품 설명 원료이지 논문 test camera별 렌더 GT를 대신하지 않는다.
- 논문 README의 평가 절차가 요구하는 test manifest와 파생 렌더/GT를 별도로 확보하거나, 저자가 제공한 정확한 평가 패키지와 대응 관계를 확인해야 한다.

따라서 ShapeNet 승인만으로 29354의 textured mesh 후보는 좁혀졌지만, 논문 동일 정량평가를 막는 미확정 사항은 **7271 ShapeNet 매핑**, **두 표본의 PartNet 내부 원본 경로**, **정확한 mesh/MTL/texture 동반 파일**, **conditioning camera/transforms**, **metric-ready GT map/mask와 질문·관절 대응 manifest**다. 이 항목들이 해결되기 전에는 다운로드·전처리·평가를 시작하지 않는다.

## 공식 근거

- [PhysX-3D 고정 README](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/README.md): PartNet texture 부재로 ShapeNet 별도 배치, validation/test 목록과 평가 실행 절차.
- [PhysXNet dataset card](https://huggingface.co/datasets/Caoza/PhysX-3D): 공개 ZIP 구조와 annotation 설명.
- [PartNet-archive dataset card](https://huggingface.co/datasets/ShapeNet/PartNet-archive): gated 접근 조건과 분할 archive.
- [ShapeNetCore dataset card](https://huggingface.co/datasets/ShapeNet/ShapeNetCore): gated 접근 조건과 synset archive 목록.
- [PhysX-3D 논문 v4](https://arxiv.org/html/2507.12465v4): test 구성과 metric 정의.

이 문서는 목록·메타데이터 조사 기록만 담으며, 데이터·캐시·인증정보·대용량 파일은 Git에 추가하지 않는다.
