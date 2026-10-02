# GT-only Isaac Sim 대조군 설치 전: 호스트 GPU 접근 감사

## 결론

**지금은 설치 실행 준비가 완료된 상태가 아니다.** Codex 실행 환경에서는 2026-10-02에 `nvidia-smi`가 NVIDIA driver와 통신하지 못했고, Isaac Sim/Kit 및 URDF importer도 발견되지 않았다. 반면 기존 작업 기록에는 일반 Linux 터미널에서 RTX 5090 두 장, `torch.cuda.is_available=True`, `CUDA_VISIBLE_DEVICES=1` 계산을 확인한 사실이 있다. 이 두 관측은 서로 다른 실행 환경에서 나온 것이므로, Codex의 실패만으로 호스트 driver 장애라고 단정하지 않는다.

아래 호스트 사전검사가 지금의 일반 Linux 터미널에서 통과하면, **사용자 승인 후에만** standalone Isaac Sim을 `/home/minsujo/Desktop/SH/PHYSx/tools/isaac-sim/`에 별도로 설치할 준비가 된다. 사전검사가 실패하면 설치·다운로드·driver 변경을 시작하지 않고 그 출력만으로 원인을 분리한다.

## 일반 Linux 호스트에서 실행할 최소 확인 명령

아래 두 명령은 설치·다운로드·파일 변경 없이 GPU 조회와 작은 PyTorch CUDA 할당만 수행한다. 첫 명령의 physical GPU index `1`과 두 번째 명령의 `CUDA_VISIBLE_DEVICES=1`은 같은 GPU를 가리킨다. 후자의 프로세스 안에서는 그 GPU가 logical index `0`으로 보이는 것이 정상이다.

```bash
nvidia-smi --query-gpu=index,name,uuid,driver_version,memory.total --format=csv,noheader,nounits
```

```bash
CUDA_VISIBLE_DEVICES=1 /home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python -B - <<'PY'
import os
import torch
print("CUDA_VISIBLE_DEVICES=", os.environ.get("CUDA_VISIBLE_DEVICES"))
print("torch=", torch.__version__)
print("cuda_available=", torch.cuda.is_available())
print("visible_gpu_count=", torch.cuda.device_count())
if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
    raise SystemExit("GPU 1 is not available to the selected physxgen process")
print("logical_0_name=", torch.cuda.get_device_name(0))
PY
```

### 판정 규칙

| 일반 호스트 결과 | Codex 결과 | 판정 |
| --- | --- | --- |
| 두 명령 모두 통과 | Codex `nvidia-smi` 실패 | **Codex 실행 환경의 GPU 접근 제한/격리 가능성이 가장 큼**. 이 기록만으로 driver 장애라고 부르지 않음. |
| `nvidia-smi` 또는 PyTorch 확인도 실패 | Codex 실패와 동일 | **호스트 GPU/driver 사전조건 미충족**. Isaac 설치 전에 시스템 관리자 또는 driver 담당자가 원인을 조사해야 함. |
| `nvidia-smi`만 통과하고 PyTorch가 실패 | Codex 실패와 무관하게 | `physxgen` CUDA/PyTorch 경로의 별도 문제. Isaac 설치 승인 전에 해결 범위와 환경 분리를 재검토. |

현재 이 문서는 첫 행의 과거 관측을 참고할 뿐, 위 명령의 **현재 출력은 아직 기록하지 않았다**. 따라서 현재 driver 상태의 확정 판정은 `PENDING_HOST_PREFLIGHT`다.

## 공식 Isaac Sim 설치 가능성

현재 작업 루트의 여유 공간은 386,058,883,072 bytes(약 360 GiB)다. NVIDIA 공식 [Isaac Sim Requirements](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html)는 x86_64 Ubuntu 22.04/24.04, 최소 50 GB SSD, RTX GPU 및 Linux tested driver `595.58.03`을 제시한다. GPU 표에는 RTX 4080(최소), RTX 5080(good), RTX PRO 6000 Blackwell(ideal)이 명시되어 있지만 RTX 5090을 개별적으로 시험했다고 적혀 있지는 않다. 그러므로 RTX 5090은 호환이라고 선결론 내리지 않고, 설치 후 공식 compatibility checker로 실제 판정한다.

공식 [Quick Install](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/quick-install.html)과 [Workstation Installation](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_workstation.html)에 따르면 Linux standalone은 release archive를 풀고 `post_install.sh`, `isaac-sim.sh` 순으로 실행한다. 다운로드와 압축 해제는 함께 약 40 GB, 최소 50 GB 여유 공간이 필요하다. 현재 공간은 통과하지만 shader/cache와 향후 USD 출력 공간은 별도 여유로 남겨야 한다.

| 구성요소 | 필요 여부 | 설치 전 현재 상태 |
| --- | --- | --- |
| 동작 가능한 NVIDIA driver와 RTX 접근 | 필수 | Codex에서 미확인; 일반 호스트 preflight 대기 |
| Isaac Sim standalone/Kit runtime | 필수 | 없음 |
| `isaacsim.asset.importer.urdf` | 필수 | standalone package의 extension으로 제공·enable 필요, 현재 runtime 부재로 미검사 |
| Isaac compatibility checker | 필수 gate | runtime 설치 후 실행 |
| Nucleus/Hub | 필수 아님 | 공식 workstation 문서상 Isaac Sim 실행에 필요하지 않음 |

공식 [URDF importer](https://docs.isaacsim.omniverse.nvidia.com/latest/importer_exporter/import_urdf.html)는 `isaacsim.asset.importer.urdf`를 enable한 뒤 URDF를 USD로 변환하도록 설명한다. `collision_from_visuals`, collision type, fixed base, link density, joint target/drive 설정은 import/실험 시 명시해서 기록해야 한다.

## 충돌 위험이 가장 낮은 설치 방식

선택할 방식은 **standalone binary release를 `/home/minsujo/Desktop/SH/PHYSx/tools/isaac-sim/` 아래 독립 디렉터리에 설치**하는 것이다. Isaac의 자체 `python.sh`와 Kit runtime만 사용하고, 기존 `envs/physxgen`에는 `pip`, `conda`, extension을 설치하지 않는다. 이 방식은 현재 PhysX-3D 재현 환경의 torch/spconv/CUDA 조합과 Isaac의 Python/Kit 의존성을 섞지 않는다.

컨테이너는 headless 반복 실행에 유용하지만 Docker/NVIDIA Container Toolkit 및 GPU runtime 사전조건이 추가되고, 공식 문서도 GUI에는 workstation 설치를 권장한다. `physxgen`에 Isaac Sim Python package를 설치하는 방식은 기존 환경의 의존성 충돌 위험 때문에 사용하지 않는다. 설치 후 cache/config/log도 `tools/isaac-sim/` 아래 별도 경로로 지정해 기존 홈/재현 cache와 분리할 계획이다.

## 설치 후 GT-only 시험 계획

모든 새 산출물은 별도 staging과 `04_한계및후속작업`의 새 기록 폴더에만 둔다. source, checkpoint, existing generated artifact를 수정하지 않는다.

| 단계 | 10163 | 29806 | 29354 |
| --- | --- | --- | --- |
| 입력 고정 | GT `finaljson`, part OBJ 2개 SHA256 재검증 | GT `finaljson`, part OBJ 8개 SHA256 재검증 | GT `finaljson`, part OBJ 6개 SHA256 재검증 |
| GT 구조 | fixed base + 1 C rotation | fixed base + 3 C rotation | fixed-only control |
| URDF | unmodified official `urdf_gen.py` logic을 별도 GT-only working copy/wrapper로 호출 | 동일 | 동일 |
| USD | official importer로 isolated output USD 생성 | 동일 | fixed-only import 확인 |
| 물리 drive | 각 revolute joint: 범위 내 목표 5개, 왕복 10회, 초기화 3회 | 각 C joint에 같은 규약 | 움직이는 joint가 없는 fixed control |
| 범위 밖 시험 | drive가 clamp/reject 하는지 별도 기록 | 동일 | 해당 없음 |

`group_info`의 GT parent/type/axis/origin/limit은 **GT converter/simulator 대조군**에만 쓴다. 10163·29806의 automated prediction은 `INTERPRETATION_BLOCKED`, 29354는 `NO_DEPLOYABLE_JOINT_SPEC` 상태를 그대로 유지하며, GT 값이 generated-output URDF를 채우는 일은 없다.

### 계획된 산출물

- `environment.json`: Isaac version, extension version/enabled state, GPU/driver, compatibility-check 결과
- `input_hashes.csv`: GT JSON·part OBJ·URDF·USD SHA256
- object별 GT-only `*.urdf`, `*.usd` (staging만; Git 제외)
- `import_report.json`: collision, fixed base, unit/frame, mass/inertia/friction 출처
- `joint_trial.csv`: 초기화 3회, 범위 내 5 목표×왕복 10회, 범위 밖 목표의 commanded/measured state
- `contact_and_collider_report.json`: collider 존재 및 contact 상태
- object별 command/stdout/stderr/exit code, 실제 physics video(실행 성공 시 짧은 파일만 Git 검토)

공통 질량·관성·마찰 값을 사용해야 할 경우 출처를 **통제된 실험 설정**으로 표기한다. 프레임 transform을 강제로 덮어쓰는 애니메이션은 사용하지 않는다.

## 설치 전에 사용자가 결정할 사항

1. 위 일반 Linux 호스트 preflight를 실행해 현재 GPU/`physxgen` 접근 결과를 제공할지.
2. standalone Isaac Sim release 다운로드·압축 해제·shader/cache 생성을 `/home/minsujo/Desktop/SH/PHYSx/tools/isaac-sim/`에 허용할지. 약 40 GB의 일시 공간과 최소 50 GB 권고가 적용된다.
3. 호스트 preflight가 실패할 경우 driver/system 변경 권한이 있는 담당자에게 전달할지. 이 작업은 driver 변경을 수행하지 않는다.
4. compatibility checker가 통과한 뒤에만 GT-only 10163·29806·29354 대조군을 실행할지. 이 대조군은 AI 예측 성공 검증이 아니다.
