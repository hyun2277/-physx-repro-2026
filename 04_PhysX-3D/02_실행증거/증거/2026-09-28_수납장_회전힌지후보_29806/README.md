# 29806 수납장 회전 힌지 비교

`cabinet_hinge_comparison.mp4`는 기존 PhysX-3D 29806 `006.png` 결과와 PhysXNet GT 구조를 **분리하여** 보여 주는 12.17초 비교 영상이다. 논문 Table 2 재현, 완전한 관절 재현, 실제 문 동작 검증이 아니다.

| 파일 | 형식·길이 | 크기 | SHA256 |
| --- | --- | ---: | --- |
| `cabinet_hinge_comparison.mp4` | H.264, 960×540, 12 fps, 12.17 s | 163,211 bytes | `1c5ddfb237fc8dc65a71ef6d7dc7e20f9acab8890456a2279516adeaf9f31669` |
| `cabinet_hinge_comparison_poster.png` | PNG, 960×540 | 94,007 bytes | `86696c726b076b100f0ec50d0078b38d8ccf6dc2bc98058e8a624bcaa23705ad` |

## 재사용한 기존 근거

- Conditioning input: `staging/articulated-sampling-29806-20260926T220010Z-ac2c1dfab94d/datasets/PhysXNet/renders_cond/29806_/006.png`, SHA256 `89f691cce979ae2b7e86929c60541d69b1c37da7c77d7a521eca0a2b0cc7782b`.
- 생성 mesh와 공식 grouping preview: `자료확보/2026-09-27_29806_동일seed_시점_probe_결과검증/29806_000_vs_006_input_and_official_groups.png`, SHA256 `9d8d9d260f6c7f11b8389cdc34e59ebbe39711003835635e6e5d2c508ef27069`.
- GT 구조: PhysXNet 29806 JSON의 group 0 fixed base와 parent 0의 C-type rotation group 1·2·3이다. 영상의 색과 회전 호는 이 GT group structure를 읽어 만든 **도식적 GT reference**이며 생성 결과가 아니다.

## 비교 내용

- GT: 총 4 groups — fixed base 1개와 C-type 회전문 3개.
- 기존 `006.png` 공식 예측: 총 3 groups.
- 예측 group 1: 37,408 vertices, 74,802 majority faces인 의미 있는 moving region.
- 예측 group 2: 2 vertices, 2 majority faces뿐이므로 독립적인 문으로 해석하지 않는다.

따라서 이 영상은 GT의 세 문 구조와 생성 결과의 한 moving region을 비교할 뿐이다. 생성 정점과 GT part의 직접 대응이 없으므로 어떤 문을 맞췄는지, parent·axis·origin·range가 정확한지 알 수 없다. generated output에 임의 URDF, 축, 회전 범위 또는 실제 문 동작을 부여하지 않았고, 물리 시뮬레이션도 수행하지 않았다.
