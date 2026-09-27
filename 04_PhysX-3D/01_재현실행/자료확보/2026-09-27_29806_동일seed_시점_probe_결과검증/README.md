# 29806 동일-seed 입력 시점 질적 probe 결과

기존 run `20260927T061911Z-4b32fcccb880`의 SUCCESS marker와 모든 marker output hash를 CPU에서 재검증했다. 두 frame 모두 seed 1, checkpoint manifest, source HEAD, RTX 5090 물리 GPU 1, CUDA 12.8.1 overlay, GCC/G++ 12, `SPCONV_ALGO=native`, input/output channel tiling, memory-bounded GroupNorm, 28,000 MiB monitor limit, 4,607 MiB reserve를 사용했다. 각 frame의 sampling·physics decoder·mesh decoder command/environment는 동일하고 입력 PNG 경로만 다르다.

| input | raw physics / property head | mesh | 공식 num_group | 이동 group 표면 |
| --- | --- | --- | --- | --- |
| `000.png` | `[180278, 32]` / `[180278, 14]`, finite | 180,278 vertices, 360,548 faces | 2 | group 1: 23,009 vertices, 45,868 majority faces, area 0.313754, 125 components; largest 34.33% |
| `006.png` | `[202042, 32]` / `[202042, 14]`, finite | 202,042 vertices, 404,072 faces | 3 | group 1: 37,408 vertices, 74,802 majority faces, area 0.537241, 56 components; largest 47.03%. group 2: 2 vertices, 2 majority faces, area 0.00001497 |

GT는 fixed base group 0과 parent 0의 C형 회전 group 1·2·3으로 총 4 groups다. 따라서 `006.png`의 공식 group 수 3은 `000.png`의 2보다 GT 4에 가깝다. 또한 006의 주된 이동 group 1은 000보다 면적이 약 1.71배이고 연결요소 수가 125에서 56으로 줄었다. 반면 group 2는 두 정점뿐이어서 의미 있는 별도 관절 표면으로 해석하지 않았다.

이는 동일 seed에서 두 conditioning view를 비교한 단일 표본 질적 관찰이다. 006의 view가 group-count와 주된 moving surface에 영향을 준 사실을 보여 주지만, 생성 정점과 GT door part의 직접 대응이 없으므로 어떤 GT door가 맞았는지, parent·direction·position·range가 정확한지는 알 수 없다. CUDA 연산 비결정성 가능성 때문에 byte 또는 vertex 단위 mesh 동일성도 주장하지 않는다. 논문 정량평가나 일반 성능 근거가 아니다.

`29806_000_vs_006_input_and_official_groups.png`는 입력 두 장과 같은 공식 grouping 규칙으로 색칠한 생성 mesh preview를 나란히 둔 CPU 결과다. 회색은 group 0, 빨강/주황은 group 1 이상이다.
