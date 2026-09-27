# 27281 stage 7 Sparse GroupNorm OOM

대상은 기존 실행의 `07_cached_physics_mesh_decoder/attempt_02`이다. 이 조사와 수정 중 GPU, sampling, decoder는 실행하지 않았다.

## 실패 위치와 살아 있는 tensor

`decoder_report.json`의 `failure_stage`는 `physics_decoder`다. 실패 위치는 `PropertyDecoder.upsample[1]`, 즉 두 번째 `SparseSubdivideBlock3d`의 `out_layers[1]`인 `SparseGroupNorm32`다. 설정은 channels 256, groups 32, channels/group 8, eps `1e-5`, affine `true`, 입력 fp16이다. 이 값은 checkpoint config의 model_channels 2048과 공식 block 구성 `2048 → 512 → 256`, 기본 num_groups 32 및 `torch.nn.GroupNorm` 기본 eps/affine에서 확인했다.

주요 tensor 산정은 다음과 같다.

| 위치 | shape/dtype | bytes | MiB |
|---|---:|---:|---:|
| 두 번째 block 입력 | 584,192×512 fp16 | 598,212,608 | 570.5 |
| main branch subdivision | 4,673,536×512 fp16 | 4,785,700,864 | 4,564 |
| 원본 schedule의 residual subdivision | 4,673,536×512 fp16 | 4,785,700,864 | 4,564 |
| 첫 output convolution | 4,673,536×256 fp16 | 2,392,850,432 | 2,282 |
| `SparseGroupNorm32`의 `x.float()` | 4,673,536×256 fp32 | 4,785,700,864 | 4,564 |

공식 `SparseGroupNorm32.forward`는 전체 sparse tensor를 fp32로 바꾼 뒤 batch별 GroupNorm을 호출한다. OOM은 이 첫 4.46 GiB fp32 전체 복사에서 발생했다. 이후 공식 `SparseGroupNorm.forward`의 fp32 `zeros_like` 출력까지 도달했다면 같은 크기의 추가 tensor가 필요했을 것이다.

attempt 02는 `torch.inference_mode()` 안에서 physics decoder를 호출했으므로 autograd graph는 생성되지 않았다. output-channel adapter는 tile list를 저장한 뒤 `torch.cat`하지 않는다. full fp16 결과를 한 번 미리 할당하고 각 output slice에 기록하며, 이번 수정은 각 input tile의 `part`, `tile_input`, 임시 module reference도 즉시 제거한다.

## 불필요한 peak 제거

공식 block은 main branch와 residual branch를 모두 subdivision한 뒤 main `out_layers`를 실행한다. 두 branch는 더하기 전까지 독립이므로 runtime wrapper는 연산 순서만 다음처럼 바꾼다.

1. main activation → subdivision → out_layers를 완료한다.
2. 그 뒤 residual subdivision과 skip convolution을 계산한다.
3. 공식과 같은 두 결과를 더한다.

이는 normalization 범위나 convolution을 바꾸지 않으면서 GroupNorm 시점에 4,564 MiB residual subdivision tensor가 동시에 살아 있는 peak를 제거한다. 원본 source와 checkpoint는 수정하지 않는다.

## memory-bounded SparseGroupNorm32

새 runtime adapter는 batch마다, group마다 해당 group의 모든 point와 8개 channel을 하나의 모집단으로 유지한다. spatial chunk별 독립 정규화는 하지 않는다.

- pass 1: 16,384-row fp32 chunk의 합을 누적해 group mean 계산
- pass 2: 동일한 전체 범위에서 squared deviation을 누적해 biased variance 계산
- pass 3: 같은 mean/variance, eps, affine weight/bias로 정규화하고 원래 순서의 미리 할당된 fp16 출력 slice에 기록
- NaN/Inf, 빈 batch, 잘못된 channel/group divisibility, grad-enabled 실행 차단

16,384×256 fp32 chunk는 16 MiB다. value, squared-deviation temporary와 runtime margin을 3배로 잡은 chunk peak는 48 MiB다. 전체 4,564 MiB fp32 복사는 만들지 않는다.

CPU 허용오차는 결과 확인 전에 fp32 `atol=rtol=2e-5`, fp16 `atol=rtol=2e-3`으로 고정했다. batch 1/2, 비균일 batch point 수, groups 4/8, affine on/off, fp16/fp32 모두 torch GroupNorm과 독립 float64 reference를 통과했다. 최대 절대오차는 fp32 `7.152557e-7`, fp16 `0`이었다. GPU는 Codex가 실행하지 않았다. stage 7은 decoder 전에 동일 small case matrix와 중간 크기 131,072×256 fp16 GPU case를 원본 torch GroupNorm과 비교하며, 하나라도 실패하면 decoder를 시작하지 않는다.

## 메모리 정책

3초 간격 nvidia-smi 값은 표본 감시이며 절대적인 hard limit 보장이 아니다. attempt 02의 표본 peak는 24,316 MiB였지만 OOM 메시지 시점 process 사용량은 29.25 GiB였다.

대형 GroupNorm 직전 proactive guard는 CUDA free/total, PyTorch allocated/reserved와 cached-free, 미리 할당할 fp16 output, 48 MiB chunk peak를 계산한다. cached-free를 먼저 사용할 수 있다고 보되 실제 device used 증가분까지 반영해 4,607 MiB reserve를 침범하면 할당 전에 중단한다. `expandable_segments`는 fragmentation이 주원인이라고 확정할 근거가 없어 설정하지 않았다.

attempt 02의 반올림된 29.25 GiB process 사용량을 기준으로 residual subdivision 4,564 MiB를 제거하고 fp16 output 2,282 MiB와 48 MiB chunk를 더한 보수적 예상 peak는 약 27,718 MiB다. 32,607 MiB에서 약 4,889 MiB가 남아 4,607 MiB 정책보다 282 MiB 크다. 여유가 좁으므로 이 산정만으로 실행을 강행하지 않으며, 실제 GroupNorm 직전 proactive guard가 최종 판정한다. monitor limit과 reserve는 올리지 않았다.

## 판정

adapter는 원본의 batch/group 전체 정규화 범위, biased variance, eps, affine, 최종 dtype을 유지하며 CPU에서 검증 가능했다. 따라서 현재 판정은 27281 계속 진행이다. stage 7의 필수 GPU 동등성 또는 proactive reserve guard가 실패하면 실제 decoder로 진행하지 않으며, 그때는 정규화 범위를 축소하지 않고 더 작은 관절 후보 전환을 검토한다.
