# cached decoder SPCONV_ALGO 누락 수정

실패 로그: `logs/rtx5090-cached-decoder-29354/20260926T193859Z-1c6037269cfe/`

이 실행은 source/checkpoint/latent, 메모리 예산, 작은 GPU 동등성 검사를 통과한 뒤 cached physics decoder에 진입했다. `decoder.stdout.log`에는 `[SPARSE][CONV] spconv algo: auto`가 기록됐고, 큰 입력에서 adapter가 `oversized sparse operation is outside validated SubMConv3d Native scope`로 중단했다. 원본 `example.py`는 trellis import 전에 `SPCONV_ALGO=native`를 설정하지만 cached decoder child는 `example.py`를 거치지 않아 환경 설정이 없었다.

GPU 사용량의 관찰 최대는 11,352 MiB로 28,000 MiB 상한보다 낮았다. 이번 실패를 메모리, checkpoint, latent, 해상도 또는 adapter 계산 실패로 판정하지 않는다. 전체 decoder는 재실행하지 않았다.

수정:

- parent runner의 child 환경에 `SPCONV_ALGO=native`를 명시한다.
- 실행 명령 기록 `command.json`과 parent `result.json`에 요청값을 남긴다.
- child가 trellis sparse convolution module import 직후 `trellis.modules.sparse.conv.SPCONV_ALGO`를 읽는다.
- 요청값과 실제값이 모두 `native`가 아니면 모델·latent를 GPU에 올리기 전에 중단하고 `decoder_report.json`에 요청값, 실제값, status와 reason을 기록한다.
- child 종료 후 parent가 `decoder_report.json`의 실제값을 `result.json`에 반영한다.

adapter가 Native 외 알고리즘을 거부하는 규칙, cached latent, checkpoint, source, channel-tiled 계산, 28,000 MiB 상한과 4,607 MiB reserve는 변경하지 않았다. 작은 GPU 비교도 명시적인 `ConvAlgo.Native` 경로를 유지한다.

일반 Linux 터미널 명령:

```bash
python3 /home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/자료확보/run_cached_decoder_29354.py
```
