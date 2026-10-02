# GT-only URDF→USD 정적 감사

대상 staging은 `20261002T072614Z-gt-only-control`이다. 이 감사는 기존 URDF·USD·실행 로그만 읽으며, URDF 재변환, Isaac 앱 실행, 물리 drive, 자동 예측군 실행을 하지 않았다.

## 판정

**USD 검사 문제**로 판정한다. URDF 생성 단계는 C형 회전 관절을 보존했고, importer가 쓴 USD의 `Physics` variant payload에도 `PhysicsRevoluteJoint`가 있다. 이전 실행기는 root USD를 열어 기본 `none` variant를 그대로 순회했으므로 10163과 29806에서 revolute joint를 0개로 잘못 관측했다. 이는 URDF 생성 실패나 AI 모델 실패가 아니다.

| object | GT C 관절 | URDF link / joint | URDF revolute | root 기본 variant의 revolute | `Physics=physics`의 revolute | 결론 |
|---|---:|---:|---:|---:|---:|---|
| 10163 | 1 | 4 / 3 | 1 | 0 | 1 | USD 검사 범위 오류 |
| 29806 | 3 | 12 / 11 | 3 | 0 | 3 | USD 검사 범위 오류 |
| 29354 | 0 | 7 / 6 | 0 | 0 | 0 | fixed 대조와 일치 |

`audit_result.json`은 importer가 만든 local layer에서 exact USD schema type token과 `apiSchemas`를 검사한 결과다. `physics`/`physx` variant에서 10163과 29806은 각각 1개/3개의 `PhysicsRevoluteJoint`, 4개의 `PhysicsArticulationRootAPI`, 6개/14개의 `PhysicsRigidBodyAPI`를 보인다. root의 기본 `none` variant에는 joint/rigid/articulation API가 없고, collision API만 geometry payload에 남는다. 29354의 `physics` variant는 6개의 `PhysicsFixedJoint`와 9개의 rigid body API를 가지며 revolute joint는 없다.

## URDF와 GT 대조

`urdf_joint_table.csv`는 XML의 모든 link/joint를 기록한다. 10163의 `gt_C_1`은 `l_1 → abstract_1`, axis `-1 0 0`, origin `(0.5859396458, -0.1837833822, -0.1539651603)`, limit `[-π/2, +π/2]`이다. 29806의 `gt_C_1..3`은 `l_0 → abstract_1..3`, axis `(0,1,0)`, 각 limit `[-π,0]`이다. 이 값은 해당 GT `group_info`의 C-type axis/point/range에서 온다.

공식 [`urdf_gen.py`](../../../../sources/physx-4f54e750a309/urdf_gen.py)는 `physxnet/finaljson`과 `partseg`를 읽고(29–44행), C형 그룹에 axis·point를 넣고 range에 `π`를 곱해 revolute joint를 만든다(144–160행). 이번 GT-only wrapper도 이 GT 관계만 사용한 대조군이며, 자동 예측 출력은 사용하지 않았다.

## USD payload / variant 근거

각 root USD는 `Physics` variant set을 가진다. 10163·29806은 `mujoco`, `physics`, `physx`와 `none`, 29354는 `physics`와 `none`을 가진다. root에 variant 선택이 author되지 않아 기본 열린 stage는 `none`이다. `physx.usda`는 `physics.usda`를 sublayer로 포함하고 `PhysxJointAPI`를 추가한다. 따라서 다음 물리 재개 전 검사는 새 변환 없이 root의 `Physics` selection을 명시해야 한다.

| 목적 | 10163·29806 선택 | 29354 선택 |
|---|---|---|
| generic schema 확인 | `physics` | `physics` |
| PhysX API 포함 schema 확인 | `physx` | 해당 variant 없음; `physics` |

이 결론은 importer 설정에서 joint import를 끈 근거를 찾은 것이 아니다. 사용한 `URDFImporterConfig`에는 joint-disable 옵션이 없고, 실행기는 `fix_base=True`, `collision_from_visuals=True`, `collision_type="Convex Hull"`, position force drive와 stiffness/damping override만 전달했다. importer 구성 클래스는 `merge_fixed_joints`의 기본값이 `False`이고 fixed joint만 병합할 수 있다고 설명한다([설치된 config.py 36–64, 81–98행](../../../../tools/isaac-sim/exts/isaacsim.asset.importer.urdf/isaacsim/asset/importer/urdf/impl/config.py)).

## 다음 최소 단계 (아직 실행하지 않음)

`run_usd_variant_revalidation.sh`는 기존 staging USD만 Isaac의 minimal experience에서 열고 root prim의 `Physics` selection을 명시한 뒤 schema/API count를 다시 기록하는 **composition-only** runner다. URDF import, physics scene, drive, 또는 transform write는 하지 않는다. 이 검사에서 10163=1, 29806=3, 29354=0 revolute가 재확인된 뒤에만, 별도 승인을 받아 GT-only physics drive를 재개할 수 있다.

```bash
cd /home/minsujo/Desktop/SH/PHYSx && repro-records/04_PhysX-3D/04_한계및후속작업/2026-10-02_GT_only_IsaacSim_USD_static_audit/run_usd_variant_revalidation.sh
```

## 파일

- `audit_gt_only_usd.py`: no-Kit, read-only USDA/XML parser.
- `audit_result.json`: schema/API, layer arc, variant selection evidence.
- `urdf_joint_table.csv`: XML-level link/joint contract.
- `revalidate_composed_usd_variants.py` / `run_usd_variant_revalidation.sh`: existing USD only composition revalidation runner.
