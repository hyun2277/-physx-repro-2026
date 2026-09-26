# 29354 cached latent decoder 복구 준비

## 중단 실행 판정

대상 실행은 `logs/rtx5090-adapter-29354/20260926T192709Z-db921ba64aaa/`이다. source/checkpoint/input 검사, CPU 검산, 작은 GPU 동등성, 기존 table 근거까지 통과했고 25-step sampling 세 번도 완료됐다. Python traceback, spconv 오류, CUDA OOM은 없다. GPU 사용량이 18,744 MiB에서 28,276 MiB로 증가하자 설정 상한 28,000 MiB를 넘어 runner가 SIGTERM을 보냈으며 `result.json`은 `GPU memory limit reached`를 기록했다. 같은 sampling을 반복하지 않는다.

`example.stdout.log`에는 다음 큰 연산 기록이 있다.

`channel_tiled_subm: N=2,168,704, C=512, O=256, fp16, tile_channels=256, indice_key=res_256`

좌표 범위는 batch/x/y/z 기준 `[0,0,80,28]`부터 `[0,255,175,227]`이며 중복은 0이다. 따라서 adapter가 실제 실패 계층의 큰 분할 연산에 진입한 사실이 확인됐다.

주요 보존 파일:

| 파일 | bytes | SHA256 |
|---|---:|---|
| `example.stdout.log` | 355 | `6585e918c5d459130bb06e4274d95581e5be411c3b71d37855b307242b5dc8bf` |
| `sampled_latents.pt` | 3,261,109 | `a75c3d9807780eec308b383a6db406d31dab48e2a21388b70bdd6e41ab940744` |
| `preprocessed.png` | 57,797 | `a2cfc38e32ca2d44e5c41a8c52323cb63b7eee5fdface0ac48fc6499d072b776` |
| `preprocessed.json` | 129 | `c9d2662948735303ec20b434d6dce39b08dcb4bedd7745f5f036920932c8b2ff` |
| `sparse_coords.json` | 83 | `f7e85bb9a79e32334ba8c72492a573af59d849c3fd7f711eedaff8f5c8fb9db6` |

중단 시점 staging에는 `pretrain/diffusion/` 디렉터리만 있고 결과 파일은 없다.

## cached latent 검증

CPU에서 `weights_only=True`로 읽었다. geometry와 physics 좌표는 각각 int32 `[33,886,4]`, 중복 없는 33,886행이며 서로 완전히 동일하다. 두 feature는 float32 `[33,886,8]`이고 모두 유한하다. geometry 범위는 `-10.84768295288086`부터 `14.790549278259277`, physics 범위는 `-8.220571517944336`부터 `4.2908477783203125`이다. CPU RNG와 CUDA RNG 상태도 포함돼 있다. decoder 재개 입력으로 사용할 수 있다.

## decoder-only 변경과 계산 영향

`run_cached_decoder_29354.py`는 저장된 geometry/physics latent를 그대로 사용한다. 이미지 전처리, sparse structure sampler, geometry sampler, physics sampler를 반복하지 않는다. `decode_cached_29354.py`는 공식 checkpoint의 `PropertyDecoder`와 `SLatMeshDecodernew`만 순차적으로 읽고 공식 순서와 동일하게 `physics_decoder(phy)` 다음 `mesh_decoder(slat, decoded_physics, physics_skip)`을 호출한다. 원본 seed, latent, 좌표, 해상도, 두 decoder checkpoint와 adapter는 바꾸지 않는다.

물리 decoder가 끝나면 mesh decoder에 필요한 `decoded_physics`와 `physics_skip[0]`만 GPU에 유지한다. 물리 decoder 가중치는 CPU로 옮기고 참조를 제거한 뒤 `gc.collect()`와 `torch.cuda.empty_cache()`를 호출한다. 그 후 mesh decoder만 GPU에 올린다. image encoder, sparse structure decoder/flow, 두 denoiser, CLIP, gaussian/radiance decoder, property output head는 로드하지 않는다.

원본 `example.py`에서 radiance-field 출력은 후속 코드가 사용하지 않는다. gaussian 출력은 `postprocessing_utils.to_glb(outputs['gaussian'][0], outputs['mesh'][0])`에서 texture GLB 생성에 사용하므로 미사용이라고 볼 수 없다. 이번 단계는 요청 범위대로 원시 mesh와 vertex physics를 생성·재로딩한다. texture GLB, RGB/물성/affordance/description 영상, CLIP 문장 score는 생성하지 않는다. mesh/physics decoder 계산 순서는 원본과 같지만 전체 example 출력과 동일하다는 주장은 하지 않는다.

## 메모리 근거와 실행 보호

장치 총량은 32,607 MiB이고 기존 실행에서 큰 decoder 구간 증가량은 `28,276 - 18,744 = 9,532 MiB`였다. 가장 큰 두 decoder checkpoint 중 mesh decoder는 약 1,223 MiB다. runner의 보수적 예상 peak는 큰 구간 증가량 + 가장 큰 decoder checkpoint + 2,048 MiB runtime overhead, 합계 약 12,803 MiB다. 상한은 기존과 같은 28,000 MiB로 유지해 4,607 MiB를 드라이버·그래픽·급격한 할당에 남긴다. 실행 직전 free memory가 예상 peak와 이 여유의 합보다 작으면 decoder를 시작하지 않는다.

runner는 GPU 1 UUID 및 compute process 부재, source HEAD와 pyc-only 변경, 11개 checkpoint hash, cached latent hash/shape/유한성을 다시 검사한다. 작은 512→256 fp16 원본/adapter/독립 참조 비교를 통과한 뒤 decoder를 한 번 실행한다. Ctrl+C, 상한 초과, timeout, OOM과 일반 실패 모두 기존 latent를 수정하지 않으며 `result.json`에 status, reason, child exit code를 기록한다.

일반 Linux 터미널 명령:

```bash
python3 /home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/자료확보/run_cached_decoder_29354.py
```

준비 중 CPU-only 검사 로그: `logs/rtx5090-cached-decoder-29354/20260926T193418Z-69dece20a4c1/`. 실제 GPU decoder는 실행하지 않았다.
