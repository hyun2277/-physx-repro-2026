# PhysX-3D 27281 articulated single-sample runner

이 실행기는 PhysXNet test index 734, object `27281` 한 건을 대상으로 최소 자산 추출부터 raw vertex physics의 CPU 관절 분석까지 순서대로 수행한다. 논문 전체 정량평가 실행기가 아니다. conditioning render는 공식 `render_cond.py` 기본 24-view이며 논문 외관 평가의 30-view camera 조건과 같다고 간주하지 않는다.

## 실행

일반 Linux 터미널에서 다음 한 줄을 실행한다.

```bash
/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python -B /home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/자료확보/run_27281_articulated_pipeline.py
```

로그는 `/home/minsujo/Desktop/SH/PHYSx/logs/physx27281-e2e/<UTC timestamp>-<UUID>/`, 대용량 staging 산출물은 `/home/minsujo/Desktop/SH/PHYSx/staging/physx27281-e2e-<UTC timestamp>-<UUID>/`에 생성된다. 실패한 실행은 같은 명령으로 자동 재시도하지 않는다. 원인을 확인한 다음 아래처럼 해당 로그 폴더를 명시해야 검증된 성공 단계를 건너뛰고 실패 단계부터 다시 실행한다.

```bash
/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python -B /home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/자료확보/run_27281_articulated_pipeline.py --resume /home/minsujo/Desktop/SH/PHYSx/logs/physx27281-e2e/<run-id>
```

## 단계와 보호 규칙

1. 고정 source HEAD, tracked source 변경, checkpoint manifest를 검사하고 두 ZIP의 중앙 목록에서 JSON, part OBJ 7개, ShapeNet OBJ/MTL/texture만 읽어 새 staging에 쓴다. 각 member의 CRC, 크기, SHA256을 기록한다.
2. 공식 `merge_property.py`를 한 항목에 실행하고 `model.obj`, `clip.npy`, `clip_ind_new.npy`, `otherproperty.npy`를 검사한다.
3. 공식 `retrieval_texture_example.py`를 실행하고 OBJ→MTL→texture, UV/형상 유한성, ShapeNet source texture 색 연결을 검사한다. 검증기가 회색 fallback을 발견하면 실패한다.
4. portable Blender 3.0.1과 공식 `_render_cond`로 24개 PNG와 `transforms.json`을 만든다. 모든 PNG decode와 4×4 유한 camera matrix를 확인하고 가장 낮은 유효 frame `000.png`를 선택한다.
5. GPU 1 보호 검사 뒤 기존 `channel_tiled_spconv.py`의 CPU algebra, spconv 경계, 큰 shape 경계와 작은 GPU original/tiled/reference 동등성 검사를 수행한다. `SPCONV_ALGO=native`와 실제 import 경로가 맞아야 다음 단계로 간다.
6. seed 1로 공식 image preprocess, conditioning, sparse/slat/physics sampling만 수행한다. decoder들은 GPU에 올리지 않는다. 좌표 동일성·중복·shape·dtype·유한성을 검사해 `sampled_latents.pt`를 저장하고 child process를 종료한다.
7. 저장 latent를 별도 child에서 기존 cached decoder로 읽는다. physics decoder를 끝낸 뒤 그 weight를 CPU로 내리고 정리한 후 mesh decoder를 로드한다. `mesh_physics_raw.pt`와 `mesh.obj`를 생성한다.
8. CPU에서 공식 property-output checkpoint의 마지막 16채널→14채널 head와 공식 후처리를 적용한다. GT group 수 3과 공식 `num_group` 결과, group별 vertex/face/area/component를 저장한다. 공식 parent/group indexing 결과와 기존 column-index 수정 후보는 서로 다른 JSON이다. description은 공식 example/training slice 불일치가 해결되지 않아 만들지 않는다. direction/position/range는 좌표계·단위와 GT 대응 계약이 확인되기 전에는 오차를 계산하지 않는다.

각 단계의 `SUCCESS.json`에는 입력 fingerprint와 출력 hash가 있다. 재개 시 둘 다 맞는 단계만 건너뛴다. timestamp+UUID와 전역 lock이 중복 실행을 막는다. 각 child는 명령, 선택 환경, stdout/stderr, exit code를 저장한다. GPU 단계는 실행 직전 물리 GPU index 1의 UUID와 compute process를 확인하고 `CUDA_VISIBLE_DEVICES=1`로 실행한다. 실행 중 GPU 1에 다른 compute process가 나타나거나 사용량이 28,000 MiB를 넘으면 child process group을 종료한다. 전체 32,607 MiB 중 4,607 MiB는 reserve로 남긴다. Ctrl+C, 상한 초과, child 실패는 `result.json`에 서로 다른 reason/status/exit code로 남는다.

## 29354에서 재사용한 계산

- CUDA 12.8.1 per-run overlay, GCC/G++ 12, physxgen torch 2.7.1+cu128 환경
- `channel_tiled_spconv.py`, `sitecustomize.py`, `validate_candidate.py`와 Native 전용 fail-closed 범위
- physics decoder 후 weight 해제, mesh decoder 순차 로드 방식
- 28,000 MiB hard limit와 4,607 MiB reserve
- source HEAD/pycache-only tracked diff/checkpoint manifest/GPU 1 보호 규칙
- retrieval의 형상·UV·source texture 검증과 portable Blender wrapper

기존 29354 명령의 기본 동작을 유지하기 위해 render wrapper와 retrieval verifier는 object ID 인자를 생략하면 계속 `29354`를 사용한다. cached decoder의 고정 row 수만 `N×8 feature`, `N×4 int32 coordinate` 계약으로 일반화했다. adapter 계산과 checkpoint는 변경하지 않았다.

## 27281에 추가한 부분

- 공식 `finalindex.json`의 `shapenet/04379243/a7887db4982215cc5afc372fcbe94f4a` 연결 검증과 안전한 선택 member 추출
- object ID를 받는 render/retrieval 검증 경로
- decoder를 전혀 실행하지 않는 sampling-only child
- 3-group 표본용 14-channel CPU head 및 공간 관절 통계
- 단계별 hash marker, 명시적 resume, 실패/중단/미실행 구분

texture GLB와 영상은 이번 분할 실행 범위에 없으므로 생성되지 않은 것으로 기록한다. 실행 성공은 RTX 5090 환경 적응을 통한 27281 한 표본의 preprocessing·sampling·mesh/raw physics 생성 및 기본 관절 구조 검사 성공만 뜻한다. 물리 정확도, 관절 파라미터 단위, GT와 예측 group 대응, 논문 정량평가는 별도 미검증 항목이다.

## Codex 준비 단계 검증

2026-09-27에는 GPU, Blender, inference를 실행하지 않았다. `--plan`은 PhysXNet member 8개와 ShapeNet member 3개의 중앙 목록을 읽어 경로/크기/CRC를 확인했다. AST parse는 새 파일과 일반화한 세 파일 모두 통과했다. `--self-test`는 성공 marker hash가 맞을 때 한 번만 실행되는 것, 출력 변조 후 명시적 `--resume` 없이는 재실행하지 않는 것, unsafe archive path mock 차단을 확인했다. 실제 CUDA/Blender/모델 단계는 사용자의 일반 터미널 실행 전까지 미실행이다.
