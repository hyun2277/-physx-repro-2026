# 10–30표본 확장 manifest 규칙 (제안)

이 규칙은 향후 공개 자료 기반 **독립** 평가를 위한 것이며 논문 test 평가 규약이 아니다. 이번에는 추가 표본 실행·다운로드·render를 하지 않았다.

1. `val_test_list.npy`의 1,000 test 행 전체에서 `test_index`, `source_index`, `object_id`, occurrence를 먼저 고정하고, 선택 행도 원래 순서·duplicate occurrence를 바꾸지 않는다.
2. fixed, B translation, C rotation 계층의 목표 수를 실행 전에 고정한다. 성공한 표본을 근거 없이 교체하지 않는다.
3. PhysXNet JSON·part OBJ, ShapeNet mesh/MTL/texture 연결, conditioning PNG/transforms, generated mesh/property가 모두 hash 검증된 표본만 `eligible`로 둔다.
4. artifact가 없으면 임의 경로·texture 대체·mesh alignment를 만들지 않는다. 원래 test row를 `blocked`와 정확한 사유로 보존한다.
5. seed, sample 수, raw/canonical coordinate condition, moving-group screen을 manifest에 적고 변경하면 새 protocol revision을 만든다.
6. scale·geometry·articulation의 success/failed/blocked를 지표별로 분리한다. blocked/failed를 삭제하거나 0으로 치환하지 않는다.
7. parent/direction/position/range, density·affordance·description PSNR, appearance PSNR, NAP COV/MMD는 공식 대응 규약이 공개될 때까지 blocked다.

CPU evaluator 자체는 eligible artifact가 10–30개일 때 확장할 수 있다. 현재 hash 검증된 complete artifact는 이 3표본뿐이므로, 실제 10–30표본 실행 가능성은 추가 artifact 존재·무결성 확인 뒤에만 판정한다.
