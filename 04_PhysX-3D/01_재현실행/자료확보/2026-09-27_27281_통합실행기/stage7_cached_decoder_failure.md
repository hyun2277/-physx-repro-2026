# 27281 stage 7 cached decoder failure

실패 실행은 `/home/minsujo/Desktop/SH/PHYSx/logs/physx27281-e2e/20260926T204346Z-1023e34e2663/`이다. stage 1~6의 현재 input fingerprint, `SUCCESS.json`, 기록된 모든 output SHA256을 runner의 `marker_valid`로 다시 계산했고 모두 통과했다. 이 조사에서 GPU, sampling, decoder는 실행하지 않았다.

## 최초 오류

child는 exit 1이었다. 요청/실제 `SPCONV_ALGO`는 모두 `native`였고 CUDA overlay, GCC 12, adapter import 경로도 command log에 존재했다. `decoder_report.json`은 physics decoder 실행 직전까지 생성돼 있었다. 가장 안쪽 exception은 physics decoder의 두 번째 `SparseSubdivideBlock3d`에서 기존 adapter가 낸 다음 오류다.

```text
channel_tiled_spconv.py:32
RuntimeError: output itself exceeds the int32 boundary
```

첫 subdivision에서 `N=584,192, C=2,048, O=512, fp16` input-channel tiled Native 연산 두 건이 실제 로그에 남았다. 다음 subdivision은 sparse row를 8배로 늘리므로 `N=4,673,536`, `O=256` 출력이 필요하다. 출력 크기는 `4,673,536 × 256 × 2 = 2,392,850,432 bytes`로 `INT32_MAX=2,147,483,647`보다 245,366,785 bytes 크다. 기존 adapter는 spconv 호출 전에 이 조건을 의도적으로 거부했다.

nvidia-smi 최대 관찰값은 15,166 MiB로 28,000 MiB hard limit보다 낮았다. 따라서 이번 실패는 runner 메모리 상한 종료가 아니다. tile 크기, hard limit, checkpoint, resolution은 변경하지 않았다.

## latent schema

| 항목 | 29354 성공 latent | 27281 latent |
|---|---:|---:|
| 파일 SHA256 | `a75c3d9807780eec308b383a6db406d31dab48e2a21388b70bdd6e41ab940744` | `9a04f440d7cd8e9e91bf4426c06093d20a17de5298f4cc97de7ddd809c93cc7d` |
| 파일 bytes | 3,261,109 | 7,018,421 |
| keys | 동일한 6개 | 동일한 6개 |
| slat/phy coords | `[33886,4]`, int32 | `[73024,4]`, int32 |
| slat/phy feats | `[33886,8]`, float32 | `[73024,8]`, float32 |
| 좌표 동일성/중복 | slat=phy, 중복 0 | slat=phy, 중복 0 |
| feature 유한성 | 통과 | 통과 |
| RNG | CPU uint8[5056], CUDA uint8[16] list | 동일 schema |

행 수, 좌표 범위, feature 값은 표본별 sampling 결과이므로 정상적인 차이다. key, dtype, feature channel, coordinate column, RNG 직렬화 형식 차이는 없다.

## 29354 전용 가정 조사

실행 파일명에는 이전 표본 ID가 남아 있었지만 decoder 본문에는 object ID, 고정 입력/출력 경로, latent hash, 고정 group 수, fixed-object 분기, `33886` 행 수가 없다. 이전에 일반화한 계약은 nonempty `N×8 float32` feature와 matching `N×4 int32` coordinates다. 이번 수정은 이 검사를 `validate_cached_latent()`로 분리하고 중복 좌표도 거부한다. 따라서 직접 실패 원인은 sample-specific hardcoding이 아니다.

## 안전한 출력 채널 분할 후보

기존 input-channel adapter는 변경하지 않아 stage 5 성공 marker를 그대로 재사용한다. 새 `output_channel_tiled_spconv.py`는 완성 출력이 int32 byte 경계를 넘는 Native SubMConv3d에만 추가로 적용한다.

- sparse coordinates, kernel, stride/padding/dilation, checkpoint weight, bias, output channel 순서를 유지한다.
- 각 output channel 구간 안에서 기존과 같은 input-channel partial convolution을 수행하고 float32로 합산한다.
- bias는 해당 output slice에 한 번만 더한다.
- 결과를 원래 output channel 위치에 써서 full `N×O` tensor를 만든다.
- 27281에서는 float32 partial allocation까지 경계 아래가 되도록 계산된 output tile 96채널을 사용한다. 사용자가 임의로 tile 크기를 정하지 않는다.
- assert 삭제, int64 강제 치환, voxel 해상도나 checkpoint 변경은 없다.

이 새 경로는 아직 GPU에서 검증되지 않았다. stage 7 child가 decoder weight를 로드하기 전에 작은 original spconv / output-tiled / 독립 neighbourhood reference 비교를 수행하며, 고정된 fp16 허용오차 `atol=.02, rtol=.02`, reference `atol=.08, rtol=.05`, 좌표 동일성, 유한성을 모두 통과해야 실제 cached decoder로 진행한다. 이 검사는 stage 7 재개의 일부이므로 stage 1~6은 반복하지 않는다.

decoder 실패 시 `decoder_report.json`에 실패 stage와 가장 안쪽 exception을 기록하고, runner는 stderr 마지막 20줄을 `failure_stderr_tail.txt`에 보존하면서 상위 터미널에도 출력한다. 기존 실패 폴더와 빈 `staging/.../decoder`는 유지하며 다음 출력은 `decoder-attempt_02`에 쓴다.
