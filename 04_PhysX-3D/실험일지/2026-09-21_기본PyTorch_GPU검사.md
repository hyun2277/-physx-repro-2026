# 2026-09-21 — 기본 PyTorch GPU 검사

## 목적과 상태

사용자가 승인한 기본 PyTorch GPU 검사 **1회를 성공했다(exit0)**. GPU 두 장의 현재 사용 상태를 조회하고 다른 compute 프로세스가 보고되지 않은 GPU 1을 선택했다. 준비된 실행기로 256×256 FP32 행렬곱과 동기화·수치 검사를 수행했고 최대 절대 오차는 0이었다.

추가 설치·확장 빌드·모델 다운로드·추론·학습·논문 실험은 수행하지 않았다. 실패 재시도나 보호 설정 해제도 없었다. 04의 앞선 준비 문서에 적힌 “GPU 미실행”은 당시 상태이며, 이 일지는 이후 승인된 **기본 검사만** 갱신한다.

## 환경과 입력

| 항목 | 실제 기록 |
| --- | --- |
| 작업 루트 / Python | `/home/minsujo/Desktop/SH/PHYSx` / `envs/physxgen/bin/python -I -B -S` |
| 준비 코드 commit | `27e290bf6991770763f8981feb55c9dabe8218e5` |
| launcher SHA256 | `34c7b1f04bacfd11bdf4383bf8a869db2d36bbbbe2b38d13103d5c10a1b35032` |
| 수치 검사 SHA256 | `9e6ec63f4284ff860d76635ff1e16bb6eff585d80040e0831f45611e0048131e` |
| 실제 import 버전 | torch `2.7.1+cu128`, torchvision `0.22.1+cu128`, torch CUDA build `12.8` |
| GPU / 드라이버 | NVIDIA GeForce RTX 5090 / `595.84` |
| 선택 장치 | nvidia-smi index 1, Device Minor 1, `/dev/nvidia1`, PCI `0000:02:00.0` |
| UUID | `GPU-843dced4-ee97-dbb8-36c9-343fe13b7647` |
| PyTorch 논리 장치 | `cuda:0`, compute capability 12.0, `sm_120` 지원 검사 통과 |
| run_id | `20260921T072002Z-dfb832771cf4` |
| 수치 입력 / seed | 256×256 FP32 ones 두 행렬; 난수를 사용하지 않아 seed 해당 없음 |

준비된 두 소스가 기존 manifest와 일치함을 실행 전에 확인했다. source나 기존 설치용 격리 실행기를 변경하지 않았다. 지정 Python은 기존 Python 3.10.21 환경이며 이번 단계의 실제 Python 버전 명령 재실행은 생략했다.

## GPU 선택과 명령·실제 결과

16:19:06(+09:00) 조회에서 GPU 0은 374 MiB/0%, GPU 1은 64 MiB/0%였고 두 GPU의 compute 프로세스 목록은 비어 있었다. 두 GPU가 모두 사용 중일 때는 실행하지 않도록 했으며, 실제로는 메모리 사용량이 낮은 GPU 1을 선택했다. `/proc/driver/nvidia/gpus/.../information`의 UUID·Device Minor와 문자 장치 번호를 대조했다. 실행기 안에서도 선택 UUID와 compute 프로세스 목록을 다시 확인했다. 상세 [선택 근거](../증거/2026-09-21_기본PyTorch_GPU검사/selection-and-dispatch/selection.json)를 보존한다.

준비된 실행 명령은 다음과 같다. **이번에 이미 1회 실행 완료한 명령의 기록이며 재실행 지시가 아니다.**

```bash
/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python -I -B -S \
  '/home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/재현자료/2026-09-21_자료보완/gpu/gpu_check_launcher.py' \
  --execute --gpu-uuid GPU-843dced4-ee97-dbb8-36c9-343fe13b7647 --device-minor 1
```

| 단계 | 시작–종료 (2026-09-21, Asia/Seoul) | exit / 결과 | 증거 |
| --- | --- | --- | --- |
| 양 GPU 정보 및 compute 조회 | 각 command/result의 시각 참조 | 각각 0, 두 GPU 확인 / compute 목록 없음 | [GPU 정보](../증거/2026-09-21_기본PyTorch_GPU검사/selection-and-dispatch/inventory-gpus/stdout.log), [compute 조회](../증거/2026-09-21_기본PyTorch_GPU검사/selection-and-dispatch/inventory-compute-apps/result.json) |
| 외부 launcher 1회 실행 | 16:20:02.839–16:20:08.435 | 0, 약 5.596초 | [command](../증거/2026-09-21_기본PyTorch_GPU검사/selection-and-dispatch/launcher-once/command.json), [result](../증거/2026-09-21_기본PyTorch_GPU검사/selection-and-dispatch/launcher-once/result.json) |
| 격리 내부 smoke 프로세스 | 16:20:03.028–16:20:08.361 | 0, `status=passed` | [command/exit](../증거/2026-09-21_기본PyTorch_GPU검사/gpu-run/smoke.command.json), [stdout](../증거/2026-09-21_기본PyTorch_GPU검사/gpu-run/smoke.stdout.log), [stderr](../증거/2026-09-21_기본PyTorch_GPU검사/gpu-run/smoke.stderr.log) |
| 내부 조회·연산·사용량 수집 | 내부 명령 10개, 명령별 시각 기록 | 모두 0, stderr 모두 빈 파일 | [요약](../증거/2026-09-21_기본PyTorch_GPU검사/selection-and-dispatch/summary.json), [최종 상태](../증거/2026-09-21_기본PyTorch_GPU검사/gpu-run/status.json) |

수치 검사 함수의 측정 구간은 약 4.205초다. Torch와 torchvision import 후, 한 개의 논리 GPU와 torch 속성의 UUID를 확인했다. FP32 행렬곱 결과는 모든 원소가 256, 최대 절대 오차 0이었다. 실제 `libcudart`와 `libcublas`/`libcublasLt`는 지정 Python 환경의 `site-packages/nvidia`에서, `libcuda.so.595.84`는 시스템 드라이버에서 로드됐다. 시스템 CUDA 12.2나 Toolkit의 stubs를 런타임 라이브러리 경로에 넣지 않았다.

## GPU 사용량과 해석

사용량은 실행 전 1개·실행 중 5개·실행 후 1개, 총 7개 표본을 기록했다. 각 조회 소요 시간+명목 1초 간격이며 연속 계측이 아니다. 내부 명령 시각은 UTC, nvidia-smi 출력은 Asia/Seoul이다.

| 측정값 | 전·중·후 7표본의 관측 최대 |
| --- | --- |
| 전체 GPU 사용 메모리 | 714 MiB / 총 32,607 MiB |
| GPU 사용률 | 14% |
| 온도 | 38°C |
| 전력 | 70.49 W |

종료 후 메모리 표본은 64 MiB였다. 38°C/70.49 W는 종료 후 표본이고 14%는 실행 전/초기 표본에도 있으므로 “연산 중 최대”라고 해석하지 않는다. 선택 시점은 0%였으나 연산 전 표본에는 14%가 기록됐고, 직전 compute 프로세스 조회는 비어 있었다. **해당 사용률의 원인은 확인하지 않았다.** 사전 조회는 GPU 독점 예약이나 다른 그래픽 작업 부재를 보장하지 않는다.

PyTorch allocator가 보고한 최대 할당은 **9,830,400 bytes(9.375 MiB)**다. 코드의 명시적 행렬 크기와 별개로 관측한 allocator 수치이며, 드라이버 context·라이브러리 workspace·전체 GPU 메모리 최대값과 같지 않다. PID별 실시간 GPU 메모리는 수집하지 않았다. 전체 GPU 표본을 모두 이번 검사 단독 사용량으로 귀속하지 않는다.

## 실패·원인·조치·재실행 결과

- 실패/오류: 없음. 사전 조회 2개·outer launcher·내부 10개 명령 모두 exit0, stderr는 모두 비어 있었다.
- 원인/수정: 오류가 없어 해당 없음. 기존 준비 코드를 수정하지 않고 사용했다.
- 재실행: 없음. `attempt=1`, `automatic_retry=false`, inner run 디렉터리 1개를 기록했다.
- 보호: 루트 읽기 전용, PHYSx 내부만 쓰기, Python/Toolkit prefix 추가 읽기 전용, 네트워크 namespace 차단, 선택 GPU 노드만 노출했다. 실제 smoke의 경계 검사도 통과했다. 보호를 해제하거나 드라이버 설정을 변경하지 않았다.

## 증거와 검증 한계

원본 로그는 `PHYSx/logs/gpu-basic-check-20260921/` 및 `PHYSx/logs/gpu-checks/20260921T072002Z-dfb832771cf4/`에 있다. [증거 안내](../증거/2026-09-21_기본PyTorch_GPU검사/README.md)와 [파일별 크기/SHA256 manifest](../증거/2026-09-21_기본PyTorch_GPU검사/evidence-manifest.json)에 공개한 50개 파일의 원본 위치와 해시를 기록했다. 결과는 소형 JSON/텍스트이며 환경·캐시·모델·데이터 본체나 인증정보를 올리지 않았다.

현재 통과 범위는 torch/torchvision import와 기본 PyTorch GPU 수치 연산이다. torchvision GPU 연산, 두 번째 GPU의 연산, CUDA Toolkit 컴파일, FlashAttention/spconv/Kaolin/renderer/vox2seq 등 확장, 모델 추론·학습·논문 지표는 미검증이다. 이번 단계에서 환경 전체의 전후 바이트 hash 비교를 수행한 것은 아니며, 읽기 전용 mount와 검사된 소스/경로·실행 결과 범위로 보존 근거를 한정한다.

다음 단계는 **미설치 CUDA 확장들의 고정 소스·빌드 순서·호환성을 검토하는 것**이다. 실제 설치/빌드는 별도 승인 후 진행한다.

## 기록 공개 범위

원격 fetch에서 `main=27e290bf6991770763f8981feb55c9dabe8218e5`로 추가 변경이 없었고 저장소 전용 hyun2277 메모리 인증을 확인했다. 이번 새 일지와 전용 증거 폴더만 파일별로 명시해 commit·일반 push한다. 논문 1~3, 최상위 README, 다른 사람 파일이나 기존 준비 코드를 변경하지 않는다. 게시 후 원격 main과 로컬 커밋 대조 원본은 `PHYSx/logs/gpu-basic-check-20260921-publication/final-publication-receipt.json`에 기록한다.
