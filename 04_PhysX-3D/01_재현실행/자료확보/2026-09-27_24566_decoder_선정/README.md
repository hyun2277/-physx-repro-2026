# 24566 첫 cached decoder 선정과 분리 실행기

## 실제 sampling 결과와 memory gate

모든 값은 각 sampling run의 `result.json`, stage 6 `SUCCESS.json`, `sampling_report.json`, `decoder_eligibility.json`에서 읽었다. 예상 peak는 29354 성공과 27281 OOM 사이의 관측 기반 lower-bound에 10% 또는 최소 1,024 MiB의 측정 오차를 더한 gate 값이다.

| 표본 | 상태 | latent N | 최대 subdivision N×64 | peak 기준 (MiB) | 32,607 MiB 중 잔여 | 4,607 MiB reserve 대비 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 29354 | decoder 성공 | 33,886 | 2,168,704 | 실제 torch max allocated 17,731.954 | 14,875.046 | +10,268.046 |
| 27281 | mesh decoder OOM | 73,024 | 4,673,536 | OOM 시 torch allocated 30,658.560 | 1,948.440 | −2,658.560 |
| 24566 | sampling 성공, gate 적격 | 27,089 | 1,733,696 | 예상 peak+오차 17,035.724 | 15,571.276 | +10,964.276 |
| 29806 | sampling 성공, gate 적격 | 11,216 | 717,824 | 예상 peak+오차 11,268.889 | 21,338.111 | +16,731.111 |

27281의 nvidia-smi 관측 peak는 31,910 MiB로, torch allocated와 별개로 실제 장치 사용량이 28,000 MiB 상한을 넘었다. 24566과 29806은 모두 현재 gate에 적격이다. 29806의 추정 reserve 여유가 더 크지만, 두 후보가 모두 적격일 때 B형 translation을 단순한 fixed-base 구조에서 먼저 검증한다는 우선순위에 따라 24566을 첫 decoder 대상으로 선정했다. 29806은 이후 C형 rotation 검증용으로 보존한다.

## 실행 범위

`run_articulated_decoder_24566.py`는 기존 24566 sampling run의 stage 1–6 `SUCCESS.json`, input fingerprint, 모든 output size/SHA256, latent SHA256을 다시 확인한다. 그 뒤 다음 순서만 수행한다.

1. GPU 1 compute-process 보호와 예상 peak+4,607 MiB reserve proactive guard
2. input-channel tiling, output-channel tiling, memory-bounded GroupNorm의 작은 GPU 동등성 검사
3. 별도 child에서 physics decoder 실행 후 sparse intermediate를 CPU 파일로 저장하고 child 종료
4. 새 child에서 intermediate를 같은 coords/features/shape/scale로 복원한 뒤 mesh decoder 실행
5. CPU property head와 GT JSON으로 group count, movement type, parent/indexing 구조만 비교

physics→mesh 분리는 checkpoint, latent, 해상도와 계산 순서를 바꾸지 않는다. mesh decoder가 사용하는 `decoded_physics`와 `physics_skip`의 features, coordinates, sparse shape, scale을 저장·복원한다. skip은 1×1 convolution 입력이고 decoded physics는 mesh extraction에 전달되므로 process-local indice/spatial cache는 후속 계산의 입력 계약에 포함되지 않는다.

28,000 MiB 상한과 4,607 MiB reserve는 유지한다. adapter는 기존 검증된 세 구현만 사용한다. description, 논문 30-view PSNR, density·affordance 정확도, 관절 파라미터의 좌표계·단위 정확도는 이 실행 범위에서 주장하지 않는다.

## CPU/정적 검증

- 새 Python 파일 3개의 AST 구문 검사 통과
- 24566 기존 stage 1–6 SUCCESS marker와 모든 output hash 검증 통과
- latent N=27,089, N×64=1,733,696, SHA256 고정값 검증 통과
- proactive guard 정상 free-memory mock 통과, 부족한 free-memory mock 거부
- plan 모드가 decoder 실행 없이 5단계 실행 계약을 출력함을 확인

실행 명령:

```bash
/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python -B /home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/01_재현실행/자료확보/run_articulated_decoder_24566.py
```
