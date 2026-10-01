# GT URDF→USD→Isaac Sim 대조군 준비 감사

## 목적과 범위

이 문서는 다음 질문만 다룬다. **“GT 관절 정보를 이용하면 현재 환경의 URDF/USD/Isaac Sim 변환과 물리 구동이 정상인가?”**

10163·29806의 generated-output 관절 명세 판정은 이전 감사에서 `INTERPRETATION_BLOCKED`였다. 따라서 generated mesh/property/group 결과로 URDF/USD를 만들지 않았고, GT의 parent·type·axis·origin·limit을 예측군에 복사하거나 수동 보정하지 않았다. GPU 추론, Blender 렌더링, Isaac Sim 실행, USD/URDF 생성, 새 다운로드도 수행하지 않았다.

## Git 기준

- 교수님 지정 기준 commit `dc62c7df196a64840344b000a54c0ba109cfa371`은 현재 main의 조상이다.
- 2026-10-02 확인 시 local `HEAD`, `origin/main`, 원격 `main`은 모두 `0159fb73bce80eb965dcf15226251aa7cb4084e9`을 가리킨다.
- 기존 untracked 파일은 삭제·이동·추가하지 않았다.

## 현재 Isaac Sim 준비 상태: 차단

| 확인 항목 | 관찰 결과 | 판정 |
| --- | --- | --- |
| Isaac Sim standalone/Kit 설치 경로 | `/home/minsujo/.local/share/ov/pkg`, `/home/minsujo/.local/share/ov`, `/home/minsujo/isaac-sim`, `/opt/isaac-sim`, `/opt/ov` 모두 없음 | `BLOCKED` |
| 실행기 | `isaac-sim.sh`, `isaacsim.sh`, `isaac-sim.selector.sh`, `isaac-sim`, `omni`를 찾지 못함 | `BLOCKED` |
| Python runtime | 지정 `physxgen` Python에서 `omni=False`, `isaacsim=False`; `pxr=True`만 확인 | `BLOCKED`; USD Python 모듈만으로 importer/PhysX runtime은 제공되지 않음 |
| URDF importer | 설치된 extension `isaacsim.asset.importer.urdf` 또는 구버전 `omni.importer.urdf`를 확인할 Isaac Sim extension tree가 없음 | `BLOCKED` |
| GPU/driver 접근 | 이 시점의 read-only `nvidia-smi`가 “couldn't communicate with the NVIDIA driver”로 실패 | `BLOCKED`; 이 관찰만으로 시스템 driver 원인을 단정하지 않음 |

NVIDIA 공식 문서에서 URDF를 USD로 import하려면 Isaac Sim의 `isaacsim.asset.importer.urdf` extension을 활성화해야 한다고 설명한다. [URDF Importer 문서](https://docs.isaacsim.omniverse.nvidia.com/latest/robot_setup/ext_isaacsim_asset_importer_urdf.html), [USD 변환 튜토리얼](https://docs.isaacsim.omniverse.nvidia.com/latest/importer_exporter/import_urdf.html)을 기준으로 했다. 현재 이 extension을 포함한 Isaac Sim runtime 자체가 없으므로 공식 구성요소가 충족되지 않는다.

따라서 이 작업의 GT 대조군 결과는 **미실행/환경 차단**이다. 이것은 PhysX-3D 모델 실패나 GT 관절 오류가 아니다.

## GT 입력은 읽기 전용으로 확인됨

| 사례 | GT 관절 구조(대조 전용) | finaljson / partseg | 확인 |
| --- | --- | --- | --- |
| 10163 | fixed base group 0; group 1은 parent 0, type C, direction·position·range 존재 | finaljson 1개, part OBJ 2개 | hash·크기 확인 |
| 29806 | fixed base group 0; groups 1/2/3은 parent 0, type C, direction·position·range 존재 | finaljson 1개, part OBJ 8개 | hash·크기 확인 |
| 29354 | `group_info`에 group 0 하나인 fixed 대조 | finaljson 1개, part OBJ 6개 | hash·크기 확인 |

세 finaljson 및 part OBJ의 bytes/SHA256은 [gt_input_hashes.csv](gt_input_hashes.csv)에 보존했다. 이 파일의 GT field는 **변환기·시뮬레이터 대조군**에만 사용 가능한 입력이며 AI 예측 결과가 아니다.

## 공식 `urdf_gen.py`의 GT 의존성

`urdf_gen.py`는 dataset root의 `./physxnet/finaljson`과 `./physxnet/partseg`를 설정하고(`urdf_gen.py:29-35`), `finaljson/<id>.json`을 열어 `group_info`를 사용한다(`:39-45`). visual mesh도 `partseg/<id>/objs/<part>.obj`에서 읽는다(`:58-62`, `:79-83`, `:98-102`). B/C 관절의 parent, type, axis, origin, limit은 `group_info`의 `mov`에서 직접 가져온다(`:109-160`).

따라서 이 파일은 generated output converter가 아니라 **GT 대조군 생성기**다. 또한 visual mesh와 고정 joint는 만들지만 `<collision>` element를 만들지 않으며, inertial 값은 모든 link에 mass `1.0`, inertia diagonal `1.0`을 하드코딩한다(`:13-18`). 마찰, collider 형상, 안정적인 mass/inertia 추정, joint drive는 이 코드에서 제공되지 않는다.

## 설치 후에만 수행할 GT 대조군 protocol

아래는 실행 계획일 뿐 아직 적용된 설정이 아니다.

1. Isaac Sim 버전과 importer extension 이름·버전을 기록하고, GT-only URDF를 별도 staging에 생성한다.
2. part OBJ를 collision mesh로 쓸지, convex decomposition 등 별도 collider를 쓸지 명시한다. base는 fixed로 설정한다.
3. `group_info`가 제공하는 C/B type, parent, direction, position, range를 그대로 사용한다. 좌표 frame, 길이 단위, 각도 단위, mass/inertia, friction의 출처를 URDF/USD 단계별로 기록한다. `urdf_gen.py` C type의 range에 `pi`를 곱하는 동작(`:160`)도 별도 검증한다.
4. 각 관절에서 range 안의 목표 위치 5개, 왕복 10회, 초기화 3회를 joint drive로 수행한다. range 밖 목표는 별도 시험으로 분리한다.
5. 매 frame transform을 덮어쓰는 애니메이션은 사용하지 않는다. drive command, joint state, frame transform, contact/collider 상태를 로그로 남긴다.

현재는 Isaac Sim runtime, URDF importer, 정상 driver 접근이 없으므로 위 protocol을 실행하지 않았다. 설치·driver 변경·다운로드는 이번 범위 밖이다.
