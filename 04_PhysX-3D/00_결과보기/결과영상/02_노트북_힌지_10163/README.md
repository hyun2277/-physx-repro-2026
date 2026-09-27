# 노트북 힌지 검출 후보: PhysXNet 10163

이 폴더는 ShapeNet laptop category `03642806`에 연결된 PhysXNet 표본 10163의
**3D 생성·예측 관절 그룹 비교** 증거다. 실제 힌지 동작, URDF/USD 변환, 시뮬레이션,
축·원점·회전 범위 정확도 또는 논문 정량평가를 검증한 결과가 아니다.

## 읽기 전용 후보 선정

공식 `finalindex.json`, PhysXNet ZIP 중앙 목록, `finaljson`을 조사했다. C형 단일
회전 group과 모든 movement field가 있는 laptop 후보 중 part 수가 가장 작은 후보를
우선했다.

| object | ShapeNet model | GT groups | part OBJ | 선택/비고 |
|---|---|---:|---:|---|
| 10163 | `3237f5cd4bca555955357c338ec9641` | fixed 0 + C 1 | 2 | 선택: 가장 단순한 단일 힌지 구조 |
| 11171 | `9cd223dd78199526628b49aa3b6c49c1` | fixed 0 + C 1 | 2 | 같은 part 수의 대안; 추가 실행하지 않음 |
| 9707 | `8b10449b4c25fb0939773ee5b5578e3` | fixed 0 + C 1 | 3 | 더 많은 part |

10163의 official mapping은 `shapenet/03642806/3237f5cd4bca555955357c338ec9641`이다.
공식 ShapeNetCore `03642806.zip`은 revision `73b692a98ee796df2f64511e0cbd4a8af2c20b27`,
229,421,338 bytes, SHA256
`56adfdd3d40a69c3bda8c542f717d40e8ee9cf910f5421b5c227bcb508940878`로 검증했다.
모델의 OBJ, MTL, `texture0.jpg`·`texture1.jpg`·`texture2.jpg`만 최소 추출했다.

## GT hinge와 prediction

GT `group_info`는 group 0 fixed base와 group 1의 parent `0`, type `C` rotation을
기록한다. JSON에는 direction `[-1, 0, 0]`, position
`[0.5859396457672119, -0.1837833821773529, -0.15396516025066376]`, range `[-0.5, 0.5]`
가 있다. 이 값들은 **GT 선정 근거**이며 generated URDF나 prediction 보완에 사용하지
않았다.

GPU 1, Native adapter, CUDA 12.8.1 overlay, GCC 12, seed 1, hard limit 28,000 MiB,
reserve 4,607 MiB에서 official merge/retrieval, 24-view conditioning, sampling,
physics/mesh child decoder와 CPU audit이 성공했다. 생성 mesh는 378,684 vertices와
757,320 faces이고 raw vertex physics는 유한했다.

공식 prediction은 `num_group=2`였다. 그러나 group 1은 vertex 5개, majority face 8개,
area fraction `7.835985e-06`, homogeneous face 3개뿐이다. 따라서 group 수가 GT와
같다는 사실은 이 표본에서 의미 있는 노트북 힌지 표면이나 GT hinge 대응을 확인하지
않는다. 축·원점·range·parent 정확도와 실제 물리 시뮬레이션은 미검증이다.

## 작은 Git evidence

| 파일 | 설명 | SHA256 |
|---|---|---|
| `conditioning_000.png` | 24-view conditioning 중 선택된 input | `1ab5c5ca9ec79bb22f0ce3a20943020de6bcbd57386d5b44f9624e53e4b19574` |
| `mesh_preview.png` | 생성 mesh의 CPU vertex projection | `76a1ac3932f9904fe1f08733afa951fb8b9d8896e834dac408aa64f2a6fa7624` |
| `predicted_group_preview.png` | official group window preview; group 1 red | `a34ae38d5f42b157476f5e330a59b4925bb1c65eb35f16254243dd07e9bb36b7` |
| `result_summary.json` | 입력·raw/audit/GT hash와 통계 | `94ce7b6c39241dc495b771b5802ab7ce07f7aa580bb3a66a5471e8e55e468b2c` |

## 발표용 비교 영상

`laptop_hinge_comparison.mp4`는 12 fps, 144 frames, 12.0 seconds의 H.264 MP4다.
GitHub 일반 파일 제한보다 충분히 작다(99,540 bytes).

1. 입력 conditioning image와 `GT: fixed base + 1 C-type rotation hinge`를 표시한다.
2. **GT REFERENCE** 장면은 위 GT JSON의 axis `[-1, 0, 0]`, origin
   `[0.5859396457672119, -0.1837833821773529, -0.15396516025066376]`, range
   `[-0.5, 0.5]`로 screen part만 열고 닫는다. 이 animation은 model prediction이 아니다.
3. generated mesh turntable에는 official predicted group window를 표시하고,
   `Predicted groups = 2, but moving group = 5 vertices` 및
   `Meaningful hinge surface not detected`를 고정 표시한다.

| 파일 | 설명 | SHA256 |
|---|---|---|
| `laptop_hinge_comparison.mp4` | GT reference와 generated mesh/group 비교 영상 | `4299165aae7bf3e6b6d8d763ec32fada07e58bd9f703b2336bc5eabc439e437f` |
| `laptop_hinge_comparison_poster.png` | generated comparison 장면 poster | `0d53075c02ee1247fade0a7cf85e1be30b956ff1b668c9a9dc5d348b3174713e` |

대용량 mesh, latent, raw tensor, checkpoint, archive, staging 및 전체 로그는 Git에
포함하지 않았다.
