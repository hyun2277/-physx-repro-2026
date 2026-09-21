# 다음 GPU 확인 단계용 준비 자료

이 폴더는 **명령과 검사 코드 준비본**이다. 이번 자료 작성에서는 실제 GPU 장치 접근, `nvidia-smi`, PyTorch import, CUDA 연산, 설치·빌드·모델 다운로드를 실행하지 않는다. 설치 단계에서 GPU를 숨기는 기존 `workspace_isolation.py`는 변경하지 않는다.

## 실행 전후의 구분

| 파일 | 기본 실행 | 미래 `--execute` 실행 |
|---|---|---|
| `gpu_check_launcher.py` | JSON 계획만 출력 | UUID/장치 경로 확인 → 격리된 드라이버 조회 → 기존 compute 작업 확인 → 작은 PyTorch 검사와 사용량 표본 기록 |
| `pytorch_smoke_check.py` | JSON 계획만 출력 | 지정 launcher가 제공한 경로·환경을 검사한 후 torch/torchvision import와 작은 CUDA 연산 수행 |
| `test_preparation.py` | 가짜 값과 mock으로 계획 생성·명령 구성을 확인 | 실제 GPU 검사 기능 없음 |

기본 모드와 `--plan`은 subprocess를 시작하지 않으며 torch를 import하거나 GPU 장치를 열지 않는다. `--execute`는 **후속 GPU 확인에 대한 사용자의 명시적인 진행 지시를 받은 뒤에만** 사용한다. 파일 작성이나 정적 검사 통과 자체가 GPU 실행 승인 또는 호환성 통과를 뜻하지 않는다.

## 지금 확인할 수 있는 계획 출력

작업 루트에서 다음 명령은 계획 JSON만 출력한다.

```bash
/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python -I -B -S \
  '/home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/재현자료/2026-09-21_자료보완/gpu/gpu_check_launcher.py' --plan
```

완전한 GPU UUID와 `Device Minor`를 알면 `--gpu-uuid`와 `--device-minor`를 추가해 실제로 사용할 명령 구성을 JSON으로 검토할 수 있다. 이때도 `--execute`를 넣지 않으면 드라이버 조회나 subprocess 실행은 없다. GPU UUID의 짧은 접두사, 단순 CUDA ordinal, 자동 전체 GPU 선택은 허용하지 않는다.

## 미래 실행 명령 — 이번 단계에서는 실행하지 않음

먼저 사용할 GPU 한 개의 **완전한 UUID**와 `/proc/driver/nvidia/gpus/<PCI주소>/information`의 **Device Minor**를 확인하고, 다른 연구의 실행 중인 작업과 사용 시간을 조율한다. CUDA ordinal과 장치 minor 번호가 같다고 가정하지 않는다.

사용자가 선택한 실제 값을 `PHYSX_GPU_UUID`, `PHYSX_GPU_MINOR`에 넣은 뒤 다음 명령을 사용한다. 값을 비워 두거나 UUID/minor 대응이 틀리면 중단된다.

```bash
/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python -I -B -S \
  '/home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/재현자료/2026-09-21_자료보완/gpu/gpu_check_launcher.py' \
  --execute --gpu-uuid "$PHYSX_GPU_UUID" --device-minor "$PHYSX_GPU_MINOR"
```

launcher는 고정된 smoke check만 실행하며 임의의 사용자 명령을 받지 않는다. 별도로 `pytorch_smoke_check.py --execute`를 직접 실행하는 방식은 사용하지 않는다.

## GPU 노출과 보존 범위

- 루트 파일시스템은 읽기 전용으로 연결하고 PHYSx 아래에서만 영구 쓰기를 허용한다. 지정 Python 환경과 CUDA Toolkit prefix는 추가로 읽기 전용이다.
- 새 `/dev` 안에 선택한 `/dev/nvidia<minor>`, `/dev/nvidiactl`, `/dev/nvidia-uvm`만 연결한다. 누락된 UVM 장치를 만들거나 `modprobe`, `sudo`, 드라이버 재설치를 실행하지 않는다.
- `CUDA_VISIBLE_DEVICES`에는 선택한 전체 UUID 하나만 지정한다. PyTorch 내부 논리 장치는 `cuda:0`으로 재번호화된다. 이 환경변수는 CUDA 가시성 설정이고, 선택한 장치 노드만 연결하는 파일시스템 제한과는 별개다.
- **공유 control/UVM 노드와 드라이버는 다른 작업과 공유된다.** 이 구성은 악성 코드나 같은 사용자 계정의 다른 프로세스에 대한 완전한 GPU 격리, GPU 독점 예약, 하드웨어 메모리 제한을 제공하지 않는다. 사전 compute 작업 조회도 이후 다른 작업이 시작되지 않는다는 보장이 아니다.
- 설치용 launcher의 GPU 숨김은 그대로 유지한다. GPU 확인용 launcher에서만 위 노드를 명시적으로 연결한다.
- 네트워크 namespace를 분리해 다운로드를 차단한다. 중첩 namespace 또는 장치 권한 때문에 실행이 거부되면 그대로 실패하고 격리를 생략하거나 권한을 자동으로 올리지 않는다.
- 환경변수는 허용 목록으로 새로 만든다. 기존 인증·SSH agent·프록시·`LD_LIBRARY_PATH`·`LD_PRELOAD`·컴파일 설정을 상속하지 않는다. HOME 값은 유지한다.
- PyTorch wheel의 라이브러리 탐색을 사용한다. CUDA Toolkit의 `lib`나 `stubs`를 `LD_LIBRARY_PATH`에 추가하지 않는다. 연산 뒤 실제 로드된 cudart/cuBLAS 경로가 지정 Python 환경 안인지 확인한다.
- 임시 파일, `/tmp`, `/var/tmp`, `/dev/shm`, 캐시와 로그는 PHYSx 아래 경로로 연결한다. 생성한 실행 기록을 자동 삭제하지 않는다.

## 미래 검사와 중단 기준

1. 실행 모드에서만 드라이버 proc 정보로 UUID/minor를 대조하고 필요한 장치 노드가 실제 문자 장치인지 확인한다.
2. 선택한 장치만 제공하는 격리 안에서 `nvidia-smi --id=<UUID>`로 GPU/드라이버 정보를 기록한다. compute 작업이 보고되면 smoke check를 시작하지 않는다.
3. 별도 단계에서 torch **2.7.1+cu128**, torchvision **0.22.1+cu128** import를 확인한다. `.pth`와 `sitecustomize`를 자동 실행하지 않도록 Python `-I -B -S`로 시작하고 지정 site-packages만 추가한다.
4. CUDA 논리 장치가 정확히 한 개이고 compute capability가 **12.0**, PyTorch 지원 arch에 **sm_120**이 있는지 확인한다. PyTorch가 UUID 속성을 제공하면 추가 대조한다.
5. FP32 256×256 행렬 두 개를 1로 채워 한 번 곱하고 synchronize한다. 결과의 모든 값은 256이어야 한다. 명시적인 tensor 크기는 작지만 CUDA context/cuBLAS workspace 크기까지 하드웨어 수준으로 제한하지는 않는다.
6. 연산 전 `usage-before`, 연산 중 `usage-*`, 정상 종료 후 `usage-final`에 선택 GPU의 전체/사용 메모리(`memory.total`, `memory.used`)·사용률·온도(`temperature.gpu`)·전력 표본을 수집한다. 같은 항목을 최초 `driver-info`에도 포함한다. 연산 중 표본 간격은 **각 조회 소요 시간 + 명목 1초 대기**이며 고정 1초 간격이 아니다. 정확한 조회 시작/종료 시각은 각 `.command.json`에 남긴다. smoke check 시간 예산은 90초이며 조회·종료 처리를 위한 짧은 추가 시간이 필요할 수 있다. 시간 초과나 조회 실패 시 실행 중인 자식 프로세스를 중단하고 드라이버 reset은 수행하지 않는다.

모든 외부 명령의 argv·시작/종료 시각·exit code와 분리된 stdout/stderr를 `logs/gpu-checks/<실행ID>/`에 보존한다. `driver-info.*`, `existing-compute-apps.*`, `usage-before.*`, `smoke.*`, `usage-*`, `status.json`을 함께 확인한다. `smoke_process_started`는 자식 프로세스 시작만 뜻하며 CUDA 연산 성공을 뜻하지 않는다. smoke가 exit 0으로 끝난 뒤 `usage-final`만 실패하면 smoke 성공 기록은 보존하고 후처리 단계 실패로 구분한다. 이 인증 없는 GPU 검사 로그에 토큰이나 전체 부모 환경변수를 기록하지 않는다.

통과하더라도 **FlashAttention, spconv, Kaolin 연산, renderer, vox2seq, 모델 추론, 학습, 논문 지표 재현**이 통과한 것은 아니다. 위 확장들의 설치·빌드·GPU 검증은 이 코드의 범위에 없다. 실제 드라이버/장치 및 namespace 동작은 아직 미래 검증 대상이다.

공식 근거: [NVIDIA UUID 선택·Device Minor 설명](https://docs.nvidia.com/deploy/nvidia-smi/), [CUDA_VISIBLE_DEVICES UUID와 논리 장치 순서](https://docs.nvidia.com/cuda/cuda-programming-guide/05-appendices/environment-variables.html).
