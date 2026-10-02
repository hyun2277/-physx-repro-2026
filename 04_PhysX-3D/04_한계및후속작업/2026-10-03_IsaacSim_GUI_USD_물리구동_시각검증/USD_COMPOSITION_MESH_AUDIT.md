# 10163 GT USD mesh 비가시 감사

## 판정

첫 GPU 0 static GUI 실행은 **GUI와 joint 구조 확인 PASS, 노트북 mesh 시각 확인 FAIL**이다. viewport에는 검은 배경과 붉은 joint/frame guide만 보였으므로 완전한 USD 시각 검증으로 기록하지 않는다. physics simulation은 0 step이며 실행하지 않았다.

geometry/physics variant 누락은 배제됐다. `gt_10163.usda`의 `Physics=physx` variant는 `payloads/Physics/physx.usda`를 payload로 선택하며, 이 파일은 `physics.usda`를 sublayer로 포함한다. root는 `base.usda → robot.usda`, geometry link는 `instances.usda → geometries.usd`로 연결된다. 실행 marker에서도 revolute 1, articulation root 1, rigid body 3, collider instance proxy 2가 resolve됐다. Kit log에는 asset resolution 또는 mesh/material load 실패가 없다.

`base.usda`의 root `extentsHint`에 ±`3.4028235e38` sentinel이 있는 것은 사실이지만, 두 번째 사람 확인에서 actual `Mesh` prim을 선택하고 `F`로 frame해도 표면이 보이지 않았다. 따라서 root `extentsHint`를 단독 원인으로 판정했던 설명은 철회한다.

## 수치 Mesh 감사

별도 renderer-free Kit 실행이 [10163_composed_mesh_audit.json](10163_composed_mesh_audit.json)을 생성했다. physics step은 0이다.

| Mesh | points | faces | indices | local/world size | det | finite/topology |
|---|---:|---:|---:|---|---:|---|
| `.../abstract_1/l_0/tn__0_` | 13,373 | 26,600 | 79,800 | `(1.438653, 0.817183, 0.239659)` | 1.0 | true/true |
| `.../tn__1_/tn__1_` | 10,971 | 21,424 | 64,272 | `(1.443179, 0.059213, 0.820626)` | 1.0 | true/true |

두 Mesh는 active/loaded, visibility `inherited`, purpose `default`, `rightHanded`, subdivision `none`이다. points는 모두 유한하고 index는 범위 내이며 모든 face는 triangle이다. world transform은 identity(첫 Mesh translation은 `5e-11` 이하)이고 determinant는 1.0이다. authored extent와 points로 재계산한 bounds가 일치한다. 따라서 **A geometry invalid/empty**와 **B transform/bounds**는 배제한다. actual Mesh `F` 후에도 검은 화면이었으므로 **D camera framing**도 현재 증상의 주원인으로 보지 않는다.

두 Mesh에는 material binding, displayColor, displayOpacity가 없다. 다만 opacity가 0으로 authored된 것은 아니며, 재질이 없는 Mesh는 일반적으로 default surface로 표시되므로 이 사실만으로 **C material/opacity**를 확정하지 않는다. GUI user config의 `scene/meshes/visible`은 `true`다. 현재 최종 분류는 **E other: valid material-free instance-proxy Mesh가 RTX viewport에서 표면으로 제출되지 않는 presentation 경로 문제, 세부 원인 미확정**이다. C와 E를 구분하기 위해 session layer에만 불투명 단색 `UsdPreviewSurface`를 바인딩하는 단일 진단을 준비했다.

## 파일 연결과 해시

| 파일 | 역할 | bytes | SHA256 |
|---|---|---:|---|
| `gt_10163.usda` | root/Physics variant | 730 | `72cee88ff5ac563e89c34e4028a9a3fe3d8b839d40f88fed4ef048e3f4fab23b` |
| `payloads/base.usda` | base/geometry hierarchy | 2,706 | `dbf60e7d52d6be782f686509ec816c48f741c53caa456f556447ad2107892269` |
| `payloads/robot.usda` | robot link/joint metadata | 1,575 | `3d727f0e2756893d2cc422ce40b0295fb134800464a5f61ed69cf84cc09661a9` |
| `payloads/instances.usda` | geometry references/collider API | 830 | `14af4e275ba55c4cdaca687ad44a1b96465bc8168ce847061503558b8593b063` |
| `payloads/geometries.usd` | binary mesh geometry | 336,727 | `d3ab97b83f089bcb75a8def7d766fe0e03adcd89b72fc46a30f0955b3d8c160f` |
| `payloads/Physics/physics.usda` | authored physics/joint schema | 3,580 | `8e4eafb18f1285616e8a6d44240d8c0d51122df7a26a86a6422bee47fc527ad5` |
| `payloads/Physics/physx.usda` | PhysX overlay and physics sublayer | 445 | `ccb7aa140ec4a191d3b3228ec67d3a137dbbb7f1d66442ef29ed772844e7afa9` |

모든 파일은 `/home/minsujo/Desktop/SH/PHYSx/staging/gt-only-isaac-control-20261002T072614Z-gt-only-control/10163/gt_10163/` 아래에 실제 존재한다. 외부 texture나 별도 mesh 파일 경로는 이 구성에서 요구되지 않는다. binary `geometries.usd`는 `Geometries`, `tn__1_`, `Mesh`, extent/face/point 토큰을 포함한다.

## 수정

원본 USD, variant, transform, geometry, lighting은 바꾸지 않는다. 다음 실행은 익명 session layer에만 `(0.15, 0.65, 0.95)`, opacity 1.0의 `UsdPreviewSurface`를 `/gt_10163/Geometry`에 inherited binding으로 적용한다. 원본 파일은 저장하지 않으며 marker에 session-only임을 기록한다. 단색에서만 보이면 C로 판정하고, 단색에서도 안 보이면 C를 배제하고 E renderer/instance presentation 진단을 계속한다.

mesh prim이 없거나 visibility/extent/layer 검사가 실패하면 사람 확인 단계로 넘기지 않는다. 자동 검사가 통과해도 노트북 mesh와 `gt_C_1` guide가 같은 viewport에 실제로 보이기 전에는 `GUI_VISIBLE=PASS`로 기록하지 않는다.
