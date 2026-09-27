# 29354 cached decoder 성공 검증

## 판정과 범위

실행 폴더 `logs/rtx5090-cached-decoder-29354/20260926T194524Z-d69f74359b60/`의 `result.json`, `decoder_report.json`, stdout/stderr와 GPU 사용량 기록을 읽고, 저장된 raw tensor 및 OBJ를 CPU에서 다시 열어 검증했다. 결과는 `status=success`, `stage=5 raw mesh and physics reload`, `child_exit_code=0`이다. 요청한 `SPCONV_ALGO`와 trellis import 후 확인한 실제 값은 모두 `native`이며 stderr는 비어 있다.

이번 결과는 **RTX 5090 환경 적응 29354 mesh·raw vertex physics decoder 성공**으로 기록한다. 앞선 실행이 만든 cached sampling latent를 별도 decoder 프로세스에서 재사용한 분할 실행이다. 단일 프로세스 원본 전체 `example.py`와 비트 단위로 동일하다고 판정하지 않는다.

## 입력과 코드 연결

| 항목 | 값 |
|---|---|
| 공식 source HEAD | `4f54e750a309fe9cd9f20816916ecc0e8a9ae594` |
| adapter가 실행된 기록 저장소 commit | `69ff25a87583749e6e0e59876203959bd9b1d017` |
| cached latent | `logs/rtx5090-adapter-29354/20260926T192709Z-db921ba64aaa/sampled_latents.pt` |
| cached latent SHA256 | `a75c3d9807780eec308b383a6db406d31dab48e2a21388b70bdd6e41ab940744` |
| mesh decoder checkpoint SHA256 | `1a460d8ea685f97c3d320b03aabd3c5ae55cf94ef4e3bd1136860521f1075dcd` |
| physics decoder checkpoint SHA256 | `ab977e5c18afd73a60cee0a44a8c75bb93debabd041dbe1b914902f3dbab38d4` |

## adapter 실행 근거

`decoder.stdout.log`에는 같은 `channel_tiled_subm` 큰 연산이 **2회** 기록됐다. 각 호출은 `N=2,168,704`, `C=512`, `O=256`, `dtype=fp16`, `tile_channels=256`, `indice_key=res_256`이다. 좌표 범위는 `[0,0,80,28]`부터 `[0,255,175,227]`이고 중복 행은 0이다. 따라서 adapter가 실제 큰 Native SubMConv3d 연산을 두 차례 처리한 사실이 확인된다.

## 메모리 기록

PyTorch가 기록한 peak allocated memory는 **17,731.954 MiB**다. 이는 이 프로세스에서 PyTorch allocator가 동시에 보유한 실제 tensor allocation의 최고치다. 마지막 측정 지점의 reserved memory는 23,378 MiB이며 peak-reserved API 값은 기록하지 않았으므로 이를 peak reserved라고 부르지 않는다.

3초 간격 `nvidia-smi` 표본의 최대 관찰값은 **20,882 MiB**다. 이는 CUDA context와 PyTorch 밖의 장치 메모리도 포함하는 프로세스 단위 관찰값이며, polling 사이의 순간 최고치는 놓칠 수 있다. 따라서 두 수치는 측정 범위와 시점이 달라 직접 동일한 지표로 해석하지 않는다.

## 산출물 재검증

| 파일 | bytes | SHA256 |
|---|---:|---|
| `staging/rtx5090-cached-decoder-29354-20260926T194524Z-d69f74359b60/mesh_physics_raw.pt` | 80,955,063 | `3afd630e568fd11dbef25a7da420e058b918a8948a656dd570c709e61d16d74c` |
| `staging/rtx5090-cached-decoder-29354-20260926T194524Z-d69f74359b60/mesh.obj` | 30,788,505 | `42fdb2fa623efb17d60bb833f37bbbdf9c11829b6b25eb723723623b99c1d431` |

CPU 재로딩 결과는 다음과 같다. 표준편차는 population 표준편차다.

| tensor | shape / dtype | 유한성 | min | max | mean | std |
|---|---|---|---:|---:|---:|---:|
| vertices | `[381856,3]`, float32 | 전부 유한 | -0.500563 | 0.500465 | 0.021606 | 0.237110 |
| faces | `[763676,3]`, int64 | index 0..381855 유효 | 0 | 381855 | - | - |
| vertex_attrs | `[381856,6]`, float32 | 전부 유한 | 0.278932 | 0.987114 | 0.685632 | 0.197003 |
| vertex_physics | `[381856,32]`, float32 | 전부 유한 | -2.481512 | 2.385813 | -0.007718 | 0.798802 |

`mesh.obj`를 `trimesh`의 `process=False`, `maintain_order=True`로 다시 읽었으며 vertex 381,856개와 face 763,676개로 raw tensor와 일치했다. raw face index도 모두 vertex 범위 안에 있다.

## 아직 검증하지 않은 항목

32개 raw physics 채널의 물리 속성 의미와 단위, 물리값 정확도, 재질·관절 정확도, 관절 출력, texture GLB와 영상 생성·디코딩, 논문 정량평가는 검증하지 않았다. 이번 단계는 저장된 mesh 및 raw vertex physics의 구조·유한성·기본 통계와 파일 일관성 검증까지다. 대용량 raw tensor와 mesh는 Git에 추가하지 않았다.
