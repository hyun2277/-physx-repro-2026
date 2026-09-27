# 수납장 힌지 구조 GT 시각화 — 29806

`cabinet_hinge_reference.mp4`는 PhysXNet 29806 JSON의 **정답 관절 구조(GT)** 를 비전공자용 2.5D 기준 도식으로 보여 주는 영상이다. PhysX-3D 예측 성공의 증거가 아니다.

| 파일 | 형식·길이 | 크기 | SHA256 |
| --- | --- | ---: | --- |
| `cabinet_hinge_reference.mp4` | H.264, 960×540, 12 fps, 9.0 s | 49,591 bytes | `2997363246c926388bbaff40171de20ff157091e281f682bbe856266eeaf1854` |
| `cabinet_hinge_reference_poster.png` | PNG, 960×540 | 69,791 bytes | `0722b1a427c886c80fb61dda114ed1694830a9df8e589f00128d14e6f13f2911` |

## GT에서 사용한 구조

- group 0: fixed cabinet body.
- group 1·2·3: 각각 parent 0의 C-type rotation door.
- 각 회전축 direction은 GT JSON의 `[0, 1, 0]`, rotation range는 `[-1.0, 0.0]` rad이다.
- 세 pivot position도 해당 JSON의 group별 값을 사용했다. 영상은 각 문을 차례로 `-0.82 rad`까지 열어, 허용 GT range 안에서 축과 회전 관계가 보이도록 했다.

영상의 색, 문 면, 축 선은 GT 관절 구조를 읽기 쉽게 만든 도식이다. 실제 물리 시뮬레이션, 충돌 검증, 동역학 계산은 수행하지 않았다. PhysX-3D 모델 출력, AI 예측 group, 관절 정확도, generated mesh는 이 영상에 포함하지 않았다.
