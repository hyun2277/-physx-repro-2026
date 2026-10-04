# 29806 cyan material/Fabric 경계 감사

대상은 GT-only 29806이며 자동 예측 결과가 아니다. 최신 isolation 진단은 manager step 12에서 정상 종료했지만 active-door schedule, recorder, MP4/GIF, 29354는 실행하지 않았다.

## 실제 PNG 판정

`isolation_10163_material_gt_C_1/2/3`은 모두 1280×720이며 cyan 전용 HSV 유사 범위로도 cyan 픽셀이 0개였다. 예상 문 bbox의 nonblack 픽셀도 0개였고 세 화면은 검정이었다. 기존 red/green/blue gate는 cyan 시험에 유효하지 않지만, 별도 cyan 검사 결과도 표시 실패다. 파일별 SHA256과 수치는 `29806_cyan_material_diagnostic_analysis.json`에 있다.

이 결과만으로 diffuse-only 재질이 실패했다고 판정할 수 없다. cyan 재질은 Physics/Fabric 활성화 뒤 기존 clone에 동적으로 bind했고 `primvars:displayColor`도 다시 author했다. 같은 경로에서 `primvars:displayColor:indices not found` 경고가 발생했고 복원 화면도 훼손됐다. 따라서 이 시험은 post-Fabric material/primvar mutation과 renderer population을 함께 바꾼 불완전한 인과 시험이다.

이전 유효한 visibility 차등에서는 source-only가 검정, red clone 단독이 검정, green clone 단독이 줄무늬, blue clone 단독이 단색이었다. source+clone 중복(z-fighting)은 배제되며, 문별 linked-clone presentation 결함은 확인됐지만 red와 green의 단일 공통 원인은 아직 확정되지 않았다.

## 10163 성공 clone과 schema 비교

| 항목 | 10163 성공 clone | 29806 door clone |
|---|---|---|
| geometry | points/counts/indices 복사, body-local | 동일 |
| orientation/subdivision | rightHanded / none | 동일 |
| normals | 별도 author 없음 | 별도 author 없음 |
| doubleSided/visibility | true / inherited | 동일 |
| displayColor | constant, 길이 1, indices 없음 | 동일 |
| displayOpacity | constant, 길이 1, indices 없음 | 동일 |
| material | diffuse+opacity, emissive 없음 | 기존 diffuse+emissive+opacity |
| extent/purpose | clone 코드에서 명시하지 않음 | extent와 default purpose 명시 |
| parent/xform | 실제 rigid body 자식, identity local xform | 각 실제 rigid body 자식, identity local xform |
| runtime xform author | 없음 | 없음 |

10163 성공 clone에도 `displayColor:indices`가 없으므로 indices 부재 자체는 치명 원인으로 볼 수 없다. 최신 경고는 Fabric 이후 displayColor primvar를 재작성한 cyan loop에서 처음 나타났다. 다음 진단은 indices를 임의 추가하지 않고, 10163과 같은 diffuse-only 재질을 physics 전에 author한다.

## Fabric 경계와 다음 진단

기존 자료는 prephysics 정상과 tensor-view 생성 뒤 실패를 보여 주지만 `initialize_physics()` 직후/tensor view 생성 전 화면이 없다. 수정 runner는 처음부터 door별 diffuse-only 재질을 사용하고 다음 경계를 분리한다.

1. prephysics linked-clone pixel gate
2. `initialize_physics()` 직후, tensor view 전 capture
3. tensor view 생성 뒤 capture
4. 첫 `update_fabric=True` closed step capture

post-Fabric cyan 재bind loop는 이 모드에서 실행하지 않는다. 이 bounded 실행에도 active-door target, recorder, MP4/GIF가 없다.

## 개폐 구현과 다음 단계

실제 active schedule은 코드에 존재한다. 실제 limit에서 open target을 `upper - 0.42*(upper-lower)`로 산출하고, 세 DOF 전체 target vector를 매 step 보내며 비구동 두 문은 0 rad closed target으로 유지한다. 3초 smoothstep opening, 1.5초 hold, 3초 closing과 wall-clock pacing이 strict recovery 뒤에 있다. isolation 모드는 그 앞에서 의도적으로 종료한다.

과거 빠른 실행은 joint span C1/C2/C3 = 1.3022/1.0521/1.0470 rad, 대응 body rotation span = 1.3022/0.9926/0.9872 rad로 실제 tensor/rigid-body 반응을 입증했다. 해당 실행은 과속, inactive drift, 시각 불연속 때문에 실패다.

표시 경계가 안정되면 다음은 제출 영상이 아니라 C1 bounded motion probe다. open target은 임의 -0.3 rad가 아니라 실제 [-pi,0] 범위의 25%인 약 -0.7854 rad로 사전 고정한다. 1.5초 closed, 3초 opening, 1초 hold, 3초 closing, 1.5초 settle 동안 C2/C3에 매 step 0 rad를 보낸다. 이 probe는 표시 안정 gate 통과 뒤에만 준비·실행한다.

현재 판정: `DISPLAY_BOUNDARY_DIAGNOSTIC_PREPARED_HOST_EXECUTION_REQUIRED`. Physics 개폐와 영상은 미실행이며 29354는 차단 상태다.
