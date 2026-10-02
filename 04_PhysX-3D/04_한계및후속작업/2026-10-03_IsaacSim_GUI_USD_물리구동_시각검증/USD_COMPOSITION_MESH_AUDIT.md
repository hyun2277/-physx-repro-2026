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

두 Mesh에는 material binding, displayColor, displayOpacity가 없다. GUI user config의 `scene/meshes/visible`은 `true`다. 첫 단색 실행은 session layer의 **`/gt_10163/Geometry` ancestor**에 `material:binding -> /__PhysXDiagnostic/Material`을 author했다. 사람 확인에서 청록색 표면은 보이지 않았고, Fabric은 `material:binding not found for path /gt_10163/Geometry/world/l_1/abstract_1`을 경고했다. 즉 instance proxy 실제 Mesh에 direct relationship이 제출됐다는 증거가 없다. 따라서 C를 배제하거나 E를 확정하지 않고 현재 상태를 **`C_OR_E_UNRESOLVED`**로 정정한다.

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

원본 USD, variant, transform, geometry는 바꾸지 않는다. 다음 실행은 composed instance proxy의 points·triangle topology와 world transform을 anonymous session layer의 일반 `UsdGeom.Mesh` 두 개로 복사한다. 복제본은 `doubleSided=true`, visibility `inherited`, direct `material:binding`, displayColor/opacity를 갖는다. 같은 stage에 주황색 reference cube와 조명을 둔다. renderer-free 정적 검산에서 복제 Mesh는 원본과 같은 13,373/10,971 points·26,600/21,424 triangles·bounds를 가지며, 두 direct binding과 computed binding이 모두 `/__PhysXDiagnostic/Material`로 resolve됐다.

다음 사람 확인 판정은 (1) cube+복제 Mesh 둘 다 표시: 원본 instance/material presentation 문제, (2) cube만 표시: 복제 Mesh renderer 속성/topology 경로 문제, (3) 둘 다 미표시: GUI renderer/presentation 문제다.

mesh prim이 없거나 visibility/extent/layer 검사가 실패하면 사람 확인 단계로 넘기지 않는다. 자동 검사가 통과해도 노트북 mesh와 `gt_C_1` guide가 같은 viewport에 실제로 보이기 전에는 `GUI_VISIBLE=PASS`로 기록하지 않는다.

## clone-mesh 사람 확인 후 판정 갱신

2026-10-03 사람 확인에서 GPU 0 Isaac GUI와 viewport, 주황색 `ReferenceCube`, 흰색 받침과 세워진 화면 형태의 `CloneMesh_0/1`, 조명이 함께 보였다. 이로써 전역 GUI renderer 실패와 원본 points/topology 이상은 배제했으며, 비가시 원인은 **원본 USD의 instance/material presentation 경로**로 좁혀졌다. 과거 `C_OR_E_UNRESOLVED`는 이 확인 전 단계의 판정이며, renderer 전체와 topology를 포함한 포괄적 미확정 상태로 유지하지 않는다. 원본 instance presentation 내부의 세부 원인은 아직 확정하지 않았다.

이 화면은 session layer에 만든 정적 일반 Mesh 복제본이다. 원본 instance가 그대로 표시됐다는 증거도, physics가 실행됐다는 증거도 아니다. 사람 확인 screenshot은 Windows `C:\Users\sh050\Desktop\physX\1003\10163_clone_mesh_visible_diagnostic.png`, 188,129 bytes, SHA256 `6784dcafd76968878ccc3a073e0bbe1a42a798f5713a8683d34ff8b5a66b546b`에만 보존됐다. Linux/Git 파일로 기록하지 않는다.
