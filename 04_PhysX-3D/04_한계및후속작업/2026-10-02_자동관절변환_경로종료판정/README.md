# 자동 관절 USD/Isaac 변환 경로 종료 판정

## 판정

현재 공개 PhysX-3D 경로에서 **제조형 물체 추가 확대와 generated-output 기반 자동 관절 USD/Isaac Sim 변환을 중단한다.** 이 판정은 모델·데이터의 삭제나 기존 public-only 재현 결과의 무효화를 뜻하지 않는다. 공개된 출력 contract만으로 실행 가능한 joint specification을 만들 수 없다는 범위 판정이다.

## 근거

1. **10163·29806: `INTERPRETATION_BLOCKED`.** 기존 generated mesh와 property output에는 group, raw parent/type, 8개 movement 값이 남아 있다. 그러나 공식 `example.py`의 parent mask는 기존 감사에서 shape mismatch를 냈고, movement 8채널의 배치, 좌표계, 길이·각도 단위, 정규화 역변환은 공개 코드에서 확인되지 않았다. 따라서 parent, joint type, axis, origin, lower/upper limit의 해석 가능한 명세를 AI 출력만으로 작성할 수 없다. [생성 결과 관절 명세 감사](../2026-09-29_생성결과_관절명세_감사/README.md)
2. **29354: `NO_DEPLOYABLE_JOINT_SPEC`.** 고정 GT 대조 사례의 저장된 결과에는 raw 32채널과 group 감사는 있으나, 실행 가능한 14채널 property head 결과가 보존되어 있지 않다. 공식 group 식은 6 vertices의 극소 group 1 때문에 2 groups를 만들지만 homogeneous triangle은 0개다. 이 결과에서 deployable joint field를 만들 수 없다. [동일 감사](../2026-09-29_생성결과_관절명세_감사/README.md)
3. **공식 `urdf_gen.py`는 GT 대조군 도구다.** 이 파일은 `physxnet/finaljson`, `group_info`, `partseg`를 직접 읽고 GT parent/type/axis/origin/limit으로 URDF를 만든다. generated mesh/property/group을 직접 입력으로 받는 변환기는 아니다. 그러므로 GT field를 AI 예측군에 복사해 자동 변환 성공처럼 사용할 수 없다. [GT URDF/USD/Isaac Sim 대조군 준비 감사](../2026-10-02_GT_URDF_USD_IsaacSim_대조군_준비감사/README.md)
4. **GT 물리 구동도 미실행이다.** 현재 확인된 환경에는 Isaac Sim/Kit runtime, URDF importer extension, 실행 가능한 NVIDIA driver 접근이 없다. 설치·다운로드·driver 변경은 이번 범위에서 수행하지 않았다. 이는 GT 관절 또는 AI 모델의 실패로 해석하지 않는다. [GT 환경 감사](../2026-10-02_GT_URDF_USD_IsaacSim_대조군_준비감사/README.md)

## 중단 범위

- 10163·29806의 generated-output을 URDF/USD/Isaac asset으로 자동 변환하지 않는다.
- GT JSON의 parent, type, axis, origin, limit을 generated output의 빈칸 보완에 사용하지 않는다.
- 수동 axis/range 지정, 임의 link 분할, URDF 보정으로 AI 관절 성공을 주장하지 않는다.
- 제조형 물체를 추가로 생성하거나 관절 변환 결과를 확장하지 않는다.

## 재개 조건

다음 중 하나가 공개 근거와 함께 확보될 때만 종료 판정을 재검토한다.

1. 저자 또는 공식 repository가 제공하는 generated-output → joint/URDF/USD 변환 규약.
2. 검증 가능한 generated joint field 정의: parent/type/axis/origin/limit의 channel layout, 좌표계, 길이·각도 단위, 정규화 역변환, group-to-link mapping.
3. 위 규약을 사용해 GT 또는 수동 보정 없이 generated output만으로 재현 가능한 joint specification을 만들 수 있다는 검증 근거.

이 조건이 충족되어도 GT 대조군과 generated-output 결과는 별도로 기록해야 하며, 관절 정확도·실제 물리 시뮬레이션 성공·논문 Table 2 재현을 자동으로 의미하지 않는다.
