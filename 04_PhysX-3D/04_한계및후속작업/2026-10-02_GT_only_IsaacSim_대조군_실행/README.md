# GT-only URDF → USD → Isaac Sim 물리 대조군: attempt 1

## 판정

**물리 구동 미실행 / 실패.** 이 대조군은 AI generated-output을 사용하지 않았다. 10163·29806의 generated prediction은 계속 `INTERPRETATION_BLOCKED`, 29354는 `NO_DEPLOYABLE_JOINT_SPEC`이다.

실행 ID `20261002T072614Z-gt-only-control`은 GT finaljson/group_info/partseg만 읽었다. 별도 staging에 GT URDF와 USD를 생성했으므로 URDF importer의 파일 변환 단계는 완료됐다. 그러나 importer가 연 USD stage에서 `UsdPhysics.RevoluteJoint`가 0개로 관측됐다.

| case | GT C joints | URDF/USD 생성 | imported-stage revolute count | drive 시험 |
|---|---:|---|---:|---|
| 10163 | 1 | 성공 | 0 | 미시작 |
| 29806 | 3 | 성공 | 0 | 미시작 |
| 29354 | 0 | 성공 | 0 | fixed 대조로는 일치하지만 collider/fixed-base payload 검증 미완료 |

따라서 target 5개, 왕복 10회, 초기화 3회, range 밖 target 및 contact 검사는 실행하지 않았다. 영상도 만들지 않았다.

## 근거

- source HEAD: `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`
- 공식 `urdf_gen.py:29–45`는 GT `finaljson/group_info`를, `:58–62, :79–83, :98–102`는 GT part OBJ를 쓴다.
- C type은 `:144–160`에서 GT axis·origin·range를 쓰고 range에 `π`를 곱한다.
- attempt runner는 이 GT-only 관계를 별도 wrapper로 재현하고, collision mesh·fixed base와 mass 1 kg/link, diagonal inertia [1,1,1] kg·m², drive stiffness 100, damping 10을 **통제 실험 설정**으로 명시했다.
- 실제 결과: `/home/minsujo/Desktop/SH/PHYSx/staging/gt-only-isaac-control-20261002T072614Z-gt-only-control/result.json`; raw stdout/stderr: `/home/minsujo/Desktop/SH/PHYSx/logs/gt-only-isaac-control/20261002T072614Z-gt-only-control/`.

## 실패 처리와 다음 조치

첫 runner는 revolute count가 0이어도 `GT_ONLY_CONTROL=PASS` marker를 냈다. 이는 변환기 성공이나 물리 구동 성공이 아니다. runner는 이제 articulated GT case에서 imported stage의 revolute joint count가 GT C joint 수와 다르면 즉시 실패하도록 수정됐다.

다음 재개 전에는 importer output의 payload/Physics variant 선택과 stage traversal 범위를 읽기 전용으로 검증해야 한다. joint가 확인되기 전에는 drive·contact·영상 시험을 재시도하지 않는다. GPU 1 단독, IOMMU 기록, P2P/multi-GPU 미사용 정책을 유지한다.
