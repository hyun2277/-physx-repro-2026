# PhysX-3D 관절 검증 최소 표본 읽기 전용 선정

## 조사 범위

로컬 `PhysXNet.zip`과 `04379243.zip`의 중앙 목록, test subset의 압축된 JSON, 선택 후보의 MTL, 고정 source HEAD `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`의 `val_test_list.npy`와 `finalindex.json`만 읽었다. ZIP member를 추출하지 않았고 GPU, decoder, Blender, 전처리, 설치 및 다운로드를 실행하지 않았다.

공식 correspondence 기록에 따라 `val_test_list.npy[1000:]`을 1,000개 test subset으로 사용했다. 따라서 object `27281`은 **test index 734(0-based)**, 원 배열 source index 1734다.

## 29354 용어 정정

29354의 GT는 group 0만 있는 fixed object다. 공식 `example.py` 규칙은 `round(max(group_id))+1=2`를 만들어 articulated로 분류한다. 따라서 **29354 표본 단위 공식 분류는 false positive**다.

이 분류 판정과 공간 분석은 별개다. group 1 threshold를 넘은 정점은 6개뿐이고 세 연결요소로 흩어져 있으며 homogeneous group-1 triangle은 0개다. 즉 의미 있는 두 번째 관절 표면 영역은 형성되지 않았다. 이상치가 생긴 원인은 미확정이다. 기존 29354 문서와 result JSON도 이 두 의미를 분리하도록 최소 수정했다.

## 전체 검색 결과

test 1,000행 중 nonzero group tuple이 있는 행은 249개, 그중 `finalindex` mapping이 있는 행은 222개다. 로컬에 이미 있는 ShapeNet category `04379243`로 연결되는 행은 11개이며, 중앙 목록과 MTL을 대조해 OBJ·MTL·MTL 참조 texture가 모두 확인된 행은 9개다.

| test index | object | groups | part OBJ | movement type | ShapeNet model | texture 연결 |
|---:|---:|---:|---:|---|---|---|
| 14 | 24566 | 2 | 8 | B | `731b983cb313634fd018082a1777a5f8` | 확인 |
| 180 | 23711 | 2 | 5 | A | `62d51d3d505aec1e5ca3dca3292dd1f` | 확인 |
| 212 | 34067 | 2 | 6 | A | `fead7e0c30a347b1710801cae5dc529` | 확인 |
| 321 | 22531 | 2 | 4 | A | `4ec8d6b5c59f656359357de4ba356705` | 확인 |
| 481 | 33451 | 2 | 4 | A | `4dae8fbaa2411c5598e0d1738edd4f19` | 확인 |
| 574 | 29806 | 4 | 8 | C,C,C | `bcdf93ab467bd7d84fb315ce917a9ec2` | 확인 |
| 599 | 23787 | 5 | 8 | C,C,C,C | `462c1b0c6f14f168c3bd24f986301745` | 확인 |
| 697, 703 | 26689 | 5 | 7 | C,C,C,C | `70e3188676407076c3bd24f986301745` | texture 없음 |
| 727 | 33514 | 17 | 18 | A×16 | `3e0fb214c130556aea3f94b6bb1b2ed6` | 확인 |
| **734** | **27281** | **3** | **7** | **B,C** | **`a7887db4982215cc5afc372fcbe94f4a`** | **확인** |

249개 후보의 group/parent/type/8-value movement parameter와 mapping 상태는 [`all_articulated_test_candidates.csv`](all_articulated_test_candidates.csv), 로컬 category 11개는 [`local_04379243_candidates.csv`](local_04379243_candidates.csv)에 있다. Type A는 “접촉하지만 movement constraint 없음”이므로 group 수가 2 이상이라는 사실만으로 관절 운동 검증에 적합하다고 보지 않았다.

## 선정 후보: test 734 / object 27281

`version_1/finaljson/27281.json`은 Cabinet이며 part OBJ 7개가 중앙 목록에 존재한다.

| group | child part | parent | direction | position | range | type |
|---:|---|---|---|---|---|---|
| 0 | 0–4 | 없음 | 없음 | 없음 | 없음 | fixed base |
| 1 | 5 drawer | group 0 | `[0,0,1]` | `[0.030629,0.465853,0.427752]` | `[0,1.00361]` | B, translation |
| 2 | 6 cabinet door | group 0 | `[0,1,0]` | `[0.471018,-0.214635,0.405251]` | `[0,1]` | C, rotation about axis |

`finalindex.json`은 이를 `shapenet/04379243/a7887db4982215cc5afc372fcbe94f4a`로 연결한다. 기존 `04379243.zip` 중앙 목록에서 다음을 직접 확인했다.

- `models/model_normalized.obj`: 217,304 bytes
- `models/model_normalized.mtl`: 450 bytes
- `images/texture0.jpg`: 8,600 bytes
- MTL `map_Kd ../images/texture0.jpg`가 실제 member로 해석됨

따라서 27281은 fixed base, translation drawer, rotation door의 child/parent/type/direction/position/range GT와 part mesh, ShapeNet mesh·MTL·texture 연결을 한 표본에 갖춘 후보다. 파일별 central-directory size·CRC는 [`selected_candidate_27281.json`](selected_candidate_27281.json)에 있다.

## 다운로드 및 다음 검증 경계

추가 다운로드는 **필요하지 않으며 0 bytes**다. 필요한 category archive `04379243.zip`은 이미 로컬에 있고 정확한 크기는 **1,666,983,898 bytes**, 기존 기록의 SHA256은 `625701ed0a2de08cc28bce6fd4f3643c67ed573c6abcbba5f0cbbb5e810d0503`이다. 이번 조사에서는 hash를 다시 계산하지 않았다. `7271`의 `finalindex` mapping은 계속 없으며 임의 mapping을 만들지 않았다.

현재 자료만으로 JSON group 구성, parent-child, B/C type, direction·position·range 값, part OBJ 수, ShapeNet texture-source 연결을 검증할 수 있다. PhysXNet ZIP의 part PNG 7개는 annotation reference image이며 conditioning render가 아니다. 27281의 conditioning image와 `transforms.json`은 현재 로컬에서 확인되지 않았다.

단순 group 개수 또는 fixed/articulated 분류는 논문의 kinematic 평가가 아니다. 논문식 instantiation distance에는 prediction, GT와 prediction의 group 대응, parameter 단위·좌표계, matching 및 집계 계약이 더 필요하다. 렌더 GT map, 30-view camera, prediction accuracy도 현재 단계에서는 검증할 수 없다.
