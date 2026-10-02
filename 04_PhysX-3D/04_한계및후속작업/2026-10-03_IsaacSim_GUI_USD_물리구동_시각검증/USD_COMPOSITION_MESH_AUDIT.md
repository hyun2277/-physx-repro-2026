# 10163 GT USD mesh 비가시 감사

## 판정

첫 GPU 0 static GUI 실행은 **GUI와 joint 구조 확인 PASS, 노트북 mesh 시각 확인 FAIL**이다. viewport에는 검은 배경과 붉은 joint/frame guide만 보였으므로 완전한 USD 시각 검증으로 기록하지 않는다. physics simulation은 0 step이며 실행하지 않았다.

geometry/physics variant 누락은 배제됐고, 현재 근거가 가장 강한 원인은 **root framing에 사용된 비물리적 `extentsHint`**다. `gt_10163.usda`의 `Physics=physx` variant는 `payloads/Physics/physx.usda`를 payload로 선택하며, 이 파일은 `physics.usda`를 sublayer로 포함한다. root는 `base.usda → robot.usda`, geometry link는 `instances.usda → geometries.usd`로 연결된다. 실행 marker에서도 revolute 1, articulation root 1, rigid body 3, collider instance proxy 2가 resolve됐다. Kit log에는 asset resolution 또는 mesh/material load 실패가 없다.

반면 `base.usda`의 root `extentsHint`에는 정상 범위 `(-0.729001, -0.227238, -0.392558) … (0.714178, 0.620511, 0.663989)`와 함께 ±`3.4028235e38` sentinel이 섞여 있다. 기존 setup은 `frame_viewport_prims(..., ["/gt_10163"])`로 이 root를 frame했다. 따라서 viewport camera가 실제 노트북보다 비정상적으로 큰 root bounds를 맞췄다는 설명이 mesh 비가시 현상과 직접 부합한다. 다음 mesh-prim framing에서 형상이 보일 때 이 인과를 최종 확인하며, 그 전에는 renderer/material 문제까지 완전히 배제했다고 쓰지 않는다. 이는 원본 transform이나 joint 실패로 해석하지 않는다.

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

원본 USD, variant, transform, material, lighting은 바꾸지 않는다. 다음 실행의 setup은 composed stage의 `UsdGeom.Mesh` prim을 먼저 감사해 visibility, purpose, local extent, world transform, material binding, prim stack을 marker로 남긴다. 사용 layer의 실제 경로·bytes·SHA256도 기록한다. camera framing은 root가 아니라 확인된 mesh prim path만 대상으로 하며, 그 뒤 `gt_C_1`을 선택해 Property panel을 유지한다.

mesh prim이 없거나 visibility/extent/layer 검사가 실패하면 사람 확인 단계로 넘기지 않는다. 자동 검사가 통과해도 노트북 mesh와 `gt_C_1` guide가 같은 viewport에 실제로 보이기 전에는 `GUI_VISIBLE=PASS`로 기록하지 않는다.
