# PhysX-3D 작업 폴더 전용 설치 계획

작성·격리 재검토일: 2026-09-21 (Asia/Seoul). **실제 설치·빌드·GPU 실험·모델 다운로드는 하지 않았다.** 이전 의존성 미리보기와 이번 문서/소스 검토 및 표준 라이브러리 기반 경로 검사를 구분한다. 아래 설치 명령은 향후 설치 진행 요청을 받은 뒤 단계별로 사용할 명령이며, 문서를 통째로 실행하지 않는다.

이번 보완의 핵심은 모든 후속 명령을 동일한 격리 실행기를 거치게 하는 것과 OpenAI CLIP의 두 호출에 `download_root`를 명시하는 것이다. 버전 후보와 기존 lock은 변경하지 않았다. [변경 전 문서](installation-plan.before-isolation-review.md), [이번 검토 기록](isolation-review-log.md), [경로 검사 결과](isolation-probe-result.json)를 별도로 보존한다.

## 1. 보존 범위와 배치

시스템 `/usr/local/cuda*`, NVIDIA 드라이버, apt/dpkg 상태, 전역 alternatives, `.bashrc`, 사용자 `.condarc`, Anaconda base 및 다른 연구 환경은 변경하지 않는다. 지정 Python 환경은 `/home/minsujo/Desktop/SH/PHYSx/envs/physxgen`을 그대로 사용한다. 시스템의 누락된 CUDA 12.8을 복구하는 방식 대신, 우리 작업 폴더에 별도 Toolkit을 설치하는 계획이다.

| 용도 | 경로 (작업 루트 기준) |
|---|---|
| CUDA Toolkit 전용 prefix | `toolchains/cuda-12.8.1` |
| Python 실행 및 패키지 | `envs/physxgen` |
| 고정된 공식 코드와 확장 소스 | `sources/` |
| Conda/Pip 다운로드 캐시 | `cache/conda`, `cache/pip` |
| 모델/런타임 캐시 | `cache/huggingface`, `cache/torch`, `cache/clip`, `cache/u2net` 등 |
| 임시 파일/빌드 | `tmp`, `build` |
| 로그/후속 산출물 | `logs`, `outputs` |

전용 CUDA prefix는 activate하지 않는다. 작업용 자식 셸에서만 CUDA 경로와 컴파일러를 지정하고, Python은 항상 지정 환경의 절대경로로 실행한다. Conda가 의존성으로 설치할 GCC와 실제 빌드에 사용할 GCC를 구분한다. 모델 실행 시 시스템 CUDA 12.2가 우선 로드되지 않도록 기존 `LD_LIBRARY_PATH`를 그대로 이어받지 않는다. CUDA의 `stubs` 디렉터리를 실행 시 라이브러리 경로에 넣지 않는다.

**격리 적용 범위:** [workspace_isolation.py](workspace_isolation.py)는 작업 루트만 쓰기 가능하게 연결하고 나머지 파일시스템을 읽기 전용으로 제공한다. HOME은 그대로 두고 캐시·임시 경로를 각각 명시한다. 설치·소스 확보·모델 다운로드 명령마다 이 실행기를 호출하도록 아래 명령을 바꿨다. 기동 실패 시 내부 명령은 실행되지 않으며, 원래 셸로 돌아가 설치를 강행하지 않는다. 전역 설정을 변경하거나 보호 설정을 해제하지 않는다.

현재 Conda23.3.1은 실제 create 때 `~/.conda/environments.txt`에 등록하려고 한다. `CONDA_ENVS_PATH`로 등록 파일 위치가 바뀌지 않으며 해당 버전에는 `CONDA_REGISTER_ENVS` 해제 옵션도 없다. 소스상 쓰기 실패는 경고로 처리되지만 **읽기 전용 HOME에서 전체 설치가 성공하는지는 미검증**이다. 실제 설치 때 이 경고와 종료 코드를 확인하며, 실패하면 외부 경로를 writable로 바꾸지 않고 원인을 검토한다.

## 2. 확인된 버전과 미확인 범위

| 구성 | 고정 버전/선택 | 확인 수준 |
|---|---|---|
| Python | 기존 **3.10.21** 유지 | 지정 환경에서 실측 |
| Conda 실행기 | 기존 **23.3.1** 사용 | 버전 확인, 업데이트 없음 |
| CUDA Toolkit | **12.8.1**, NVIDIA `cuda-12.8.1` label | 전용 prefix 대상 dry-run 성공 |
| NVCC | **12.8.93** | Conda 해결 결과/공식 release notes 일치, 실제 파일 미설치 |
| Toolkit cudart | **12.8.90** | Toolkit 구성; PyTorch wheel 내 runtime 버전과 구분 |
| 실제 host compiler | **GCC/G++ 13.3.0**, `/usr/bin/gcc-13`, `/usr/bin/g++-13` | 두 실행 파일과 버전 직접 확인, 읽기만 수행 |
| Toolkit에 함께 들어올 GCC/GXX | **11.2.0**, 정확한 build는 Conda specs 참조 | Conda 의존성 해결 결과; 실제 host 선택과 별개 |
| libgcc/libstdcxx runtime | **15.2.0** | Conda 해결 결과; GCC 실행 도구 버전이 아님 |
| PyTorch | **2.7.1+cu128** | 공식 설치 조합과 cp310 Linux wheel 확인 |
| torchvision | **0.22.1+cu128** | PyTorch 대응 버전 확인 |
| Kaolin | **0.18.0**, torch2.7.1/cu128 전용 wheel | 공식 cp310 Linux wheel 확인, GPU 연산 미검증 |
| FlashAttention | **2.8.3**, 고정 SHA로 소스 빌드 후보 | sm120 및 dense/varlen 소스/API 확인, 빌드·실행 미검증 |
| spconv/cumm | **spconv-cu126 2.3.8 + cumm-cu126 0.7.11** | 메타데이터상 일치하는 **검토 후보**, RTX5090 연산 미검증 |
| xformers | 기본 계획에서 설치하지 않음 | dense/sparse에 FlashAttention 경로를 사용한다는 전제 |

전체 직접 의존성의 exact pin은 [python-direct-candidates.txt](python-direct-candidates.txt), CUDA 118개 패키지의 버전/build는 [cuda-toolkit.conda-specs.txt](cuda-toolkit.conda-specs.txt), 소스 및 모델 SHA는 [source-pins.json](source-pins.json)에 기록했다. Python 기본 목록에는 공식 `setup.sh --basic` 패키지와 CLIP용 보조 의존성, ipdb, 빌드 도구를 포함한다. 학습/웹 데모용 확장은 이번 기본 추론 환경 계획에서 제외한다.

NumPy 1.26.4 / OpenCV-headless 4.11.0.86 / SciPy 1.15.3을 후보로 고정했다. Transformers 4.51.3은 `huggingface-hub>=0.30,<1.0`, `tokenizers>=0.21,<0.22`를 요구하므로 hub 0.34.4 / tokenizers 0.21.1로 맞췄다. `hf` CLI를 위해 무조건 hub 1.x로 올리지 않는다. 빌드 도구 후보는 setuptools 75.8.0, wheel 0.45.1, packaging 24.2, ninja 1.11.1.4, cmake 3.31.6, build 1.2.2.post1이다. 이 선택은 현재 지정 환경의 일부 빌드 패키지 버전을 낮추는 **향후 계획**이며 실제 변경은 하지 않았다. 오래된 확장에 대한 빌드 성공은 별도 확인해야 한다.

## 3. GCC 14.3에 대한 정확한 판단

**NVIDIA 문서의 CUDA 12.8.1 x86_64 지원 범위는 GCC 6.x–14.x이다.** 따라서 GCC 14.3이라는 숫자만으로 CUDA 12.8과 비호환이라고 할 수 없다. 같은 major의 이후 minor도 지원한다는 정책이 있다.

하지만 이번에 선택한 **Conda 패키지 `cuda-nvcc-dev_linux-64=12.8.93=0`에는 `gcc_impl_linux-64 >=6,<14.0a0`라는 더 좁은 solver 제약**이 있다. `cuda-nvcc=12.8.93=0`은 gcc_linux-64/gxx_linux-64를 직접 요구한다. 실제 dry-run은 두 실행 도구를 11.2.0으로 골랐다. 앞선 사용자의 `cuda=12.8` 미리보기와 동일한 channel/spec 조합이라고 가정하지 않는다.

이번 빌드 계획에서는 이미 존재하는 `/usr/bin/gcc-13`, `/usr/bin/g++-13`을 명시해 **13.3.0**을 사용한다. 시스템 컴파일러를 교체하거나 기본 링크를 바꿀 필요가 없다. Python 빌드 문자열의 GCC 14.3, Conda libgcc 15.2, 실제 C/C++ 실행 도구 버전은 서로 다른 정보다.

`CC`/`CXX`는 같은 GCC 계열로 지정한다. NVCC 직접 호출에서는 `-ccbin`이 `NVCC_CCBIN`보다 우선하며, PyTorch extension은 `CC`를 NVCC host 선택에 사용할 수 있다. `CUDAHOSTCXX`는 CMake 최초 configure용 변수이고 NVCC 자체 설정 변수는 아니다. CUDA 12.8.1 표의 Ubuntu 검증 범위와 현재 Ubuntu 24.04.3도 완전히 같다고 주장하지 않는다. **지원표·solver 통과는 실제 확장 빌드 통과와 다르다.**

근거: [NVIDIA host compiler 정책](https://docs.nvidia.com/cuda/archive/12.8.1/cuda-installation-guide-linux/index.html#host-compiler-support-policy), [NVCC 환경변수](https://docs.nvidia.com/cuda/archive/12.8.1/cuda-compiler-driver-nvcc/index.html#nvcc-environment-variables), [CMake CUDAHOSTCXX](https://cmake.org/cmake/help/latest/envvar/CUDAHOSTCXX.html), [저장된 Conda metadata](conda-cuda128-dry-run.json).

## 4. 설치 격리와 다운로드 경로

### 4.1 공통 실행 방식과 이번에 확인한 범위

아래 모든 Bash 명령 블록은 절대경로 Python으로 `workspace_isolation.py`를 호출한다. Python `-I -B -S`로 사용자 Python 설정/초기화 영향을 줄이고, 실행기는 bwrap 자체에 최소 환경을 전달한다. bwrap 안에서는 `--clearenv` 후 정해진 변수만 제공한다. 이후 셸은 `--noprofile --norc`로 시작한다. 부모 셸의 환경이나 설정 파일을 수정하지 않는다.

- 외부 `/usr/local`, 시스템 CUDA12.2, 사용자 홈, Anaconda base, `/etc`, `/proc/sys`는 검사에서 읽기 전용이었다. PHYSx는 쓰기 가능했다.
- `/tmp`, `/var/tmp`는 `PHYSx/tmp`, `/dev/shm`은 `PHYSx/tmp/shm`에 연결했다. 아주 작은 임시 표식 파일로 실제 저장 위치를 확인했다. 검사 프로그램이 만든 표식만 닫을 때 정리했다.
- GPU 장치 경로는 제공하지 않고 `CUDA_VISIBLE_DEVICES`도 비운다. 이것은 설치/빌드용 실행 방식이다. 향후 GPU 실험용 장치 연결은 별도 계획이 필요하다.
- 최종 자식 환경에 기존 `LD_LIBRARY_PATH`, `LD_PRELOAD`, `LD_AUDIT`, `PYTHONPATH`, `PYTHONHOME`, `BASH_ENV`, `NVCC_*FLAGS`, `CPATH`, `LIBRARY_PATH`, `CMAKE_PREFIX_PATH` 등이 없음을 검사했다. 부모 변수에 표식을 주입한 전수 동적 검사는 하지 않았다.
- Git은 사용자/시스템 설정을 배제하고 빈 작업 폴더 내 template와 `core.hooksPath=/dev/null`을 적용한다. clone뿐 아니라 checkout/submodule에도 유지하여 기존 사용자 hook의 실행을 피한다.
- 캐시/prefix 경로가 외부 symlink로 연결되면 실행기가 중단한다. `HOME`은 원래 `/home/minsujo`를 유지한다. 캐시를 따르지 않는 코드가 외부에 쓰려고 하면 성공시키는 대신 실패하도록 한다.

**확인 수준:** 격리 기동, 검사 대상 마운트, 쓰기 핸들 거부, 임시 파일 연결, 최종 환경, Git hook 설정은 확인했다. `/etc/os-release` 쓰기 핸들은 `EACCES`로 거부됐으며 별도 `statvfs`로 읽기 전용 마운트임을 확인했다. 이를 `EROFS` 오류라고 바꾸어 기록하지 않는다. 최초 실행은 도구 샌드박스의 중첩 namespace 제한으로 실패했고, 명령별 실행 승인 후 재검사했다. 시스템 보호 설정은 변경하지 않았다. **이 검사는 실제 Conda/Pip 설치나 임의의 모든 빌드 코드의 동작을 검증한 것이 아니다.**

### 4.2 저장 위치와 설정 우선순위

모든 경로는 `/home/minsujo/Desktop/SH/PHYSx` 기준이다. 실행기의 정확한 환경변수 목록과 검사 결과 JSON을 함께 사용한다.

| 대상 | 실제 저장 경로 / 적용 방법 |
|---|---|
| Conda 다운로드·압축 해제 캐시 | `cache/conda`; `CONDA_PKGS_DIRS`, 설치 prefix는 `toolchains/cuda-12.8.1` |
| Pip 다운로드 | `cache/pip`; `--cache-dir`도 명시, `PIP_CONFIG_FILE=/dev/null` |
| 일반 임시·빌드 임시 | `tmp`; `TMPDIR/TMP/TEMP`, `/tmp`·`/var/tmp` 연결 |
| 공유 메모리 임시 파일 | `tmp/shm`; 격리 내부 `/dev/shm` 연결 |
| XDG cache/config/data/state/runtime | `cache/xdg*`, `tmp/runtime`; 각각 변수 지정 |
| PyTorch Hub·DINO 가중치/소스 | `cache/torch`; `TORCH_HOME` |
| PyTorch extension 산출물 | `build/torch-extensions`; `TORCH_EXTENSIONS_DIR` |
| Hugging Face 다운로드·xet·동적 모듈 | `cache/huggingface/{hub,assets,xet,modules,datasets}`; 각각 명시 |
| OpenAI CLIP ViT-L/14 가중치 | **`cache/clip` + 호출의 `download_root` 명시**, 아래 4.3 참고 |
| rembg/U2Net 모델 | `cache/u2net`; `U2NET_HOME` |
| CUDA PTX 디스크 캐시 | `cache/cuda`; `CUDA_CACHE_PATH` |
| Triton 캐시·dump·override | `cache/triton`, `cache/triton-dump`, `cache/triton-override` |
| Numba·Matplotlib·ImageIO·pycache | `cache/numba`, `cache/matplotlib`, `cache/imageio`, `cache/pycache` |
| 소스·모델 본체·산출물·로그 | `sources`, 해당 `pretrain` 하위, `outputs`, `logs` |

`CONDARC` 하나를 지정해도 Conda23.3.1이 시스템/사용자 설정을 모두 무시하는 것은 아니다. CLI에 channels/prefix를 명시하고 **`--no-default-packages`**로 사용자 `create_default_packages` 자동 추가를 막는다. **`--copy`**로 새 Toolkit prefix를 패키지 캐시와 hardlink로 공유하지 않게 한다. 이 옵션은 기존 환경의 링크를 바꾸지 않는다. 실제 해결 결과에 이전 exact spec 외 패키지나 다른 prefix 변경이 보이면 설치 전에 중단한다.

Pip은 `--isolated`와 명시적 캐시 인자를 함께 쓰고, 해당 pip의 `PIP_CONFIG_FILE=/dev/null` 처리로 config 파일 로드를 막는다. source 빌드의 `--no-build-isolation`은 **Python build dependency용 임시 환경을 만들지 않는 옵션**이다. 파일시스템 격리를 끄는 옵션이 아니며, bwrap 격리는 그대로 유지한다.

Transformers4.51.3의 이전 캐시 변수(`TRANSFORMERS_CACHE`, `PYTORCH_TRANSFORMERS_CACHE`, `PYTORCH_PRETRAINED_BERT_CACHE`)와 Hub의 이전 `HUGGINGFACE_HUB_CACHE`, 사용자 `TRITON_CACHE_MANAGER`는 상속하지 않는다. `HF_MODULES_CACHE`, `HF_TOKEN_PATH`도 PHYSx 아래로 지정한다. 인증정보를 환경 덤프·명령 추적·로그로 출력하지 않으며, 이번 작업에서는 로그인이나 토큰 생성/복사를 하지 않았다.

spconv2.3.8/cumm0.7.11에 존재하지 않는 `CUMM_CACHE_PATH`/`SPCONV_CACHE_PATH`로 해결했다고 하지 않는다. NVRTC 재사용은 메모리 dict이고 editable JIT 산출물은 패키지의 `PACKAGE_ROOT/core_cc`에 생긴다. 소스와 설치 환경을 PHYSx 안에 둔다. nvdiffrast0.3.3 JIT는 자체 arch 선택을 하므로 `TORCH_CUDA_ARCH_LIST=12.0`만으로 최종 타깃이 보장되지 않는다.

### 4.3 CLIP 경로 보완: 패치 후보이며 아직 적용하지 않음

고정 PhysX 소스의 `example.py:153`과 `dataset_toolkits/merge_property.py:51`은 OpenAI `clip.load`에 `download_root`를 넘기지 않는다. 고정 OpenAI CLIP은 이를 생략하면 `~/.cache/clip`을 사용한다. **`XDG_CACHE_HOME`이나 `TORCH_HOME`, 빈 `cache/clip` 폴더만으로 바뀌지 않는다.**

격리 실행기는 `PHYSX_CLIP_DOWNLOAD_ROOT=/home/minsujo/Desktop/SH/PHYSx/cache/clip`을 제공한다. 이는 우리가 정한 변수이며 **CLIP이 자동으로 읽는 변수가 아니다.** 아래처럼 호출에서 직접 전달해야 한다. 변수가 없을 때 HOME으로 돌아가는 fallback은 넣지 않는다.

```python
# example.py의 기존 clip.load 호출을 교체
clipmodel, preprocess = clip.load(
    "ViT-L/14", jit=False,
    download_root=os.environ["PHYSX_CLIP_DOWNLOAD_ROOT"],
)
# dataset_toolkits/merge_property.py의 기존 호출을 교체
model, preprocess = clip.load(
    "ViT-L/14", jit=False, device=device,
    download_root=os.environ["PHYSX_CLIP_DOWNLOAD_ROOT"],
)
```

실제 교체 diff는 [clip-cache-path.review.patch](clip-cache-path.review.patch), 원문/SHA/정적 검사 근거는 [clip-cache-review.json](clip-cache-review.json)에 남긴다. 이는 **검토용 패치이며 작업용 원본에 적용하거나 실행한 상태가 아니다.** 향후 고정 SHA로 소스를 확보한 뒤 `git apply --check`로 대조하고 적용 내역을 보존한다. 두 파일 외 새 `clip.load` 호출도 정적으로 검색한다. 완료 시점은 **첫 CLIP 가중치 다운로드 또는 `clip.load` 실행 전**이다. CLIP Python 패키지의 wheel 설치 전부터 가중치 다운로드를 요구하는 것은 아니다.

Transformers `CLIPTextModel.from_pretrained`의 HF 캐시는 위 OpenAI CLIP의 `.pt` 가중치와 별개다. `clip.load(device="cpu")`도 다운로드/모델 초기화를 수행하므로 이번 검토용 테스트로 실행하지 않는다. `torch.hub.load`나 `rembg.new_session`도 캐시 경로 확인을 위해 호출하지 않는다.

고정 CLIP 소스의 ViT-L/14 파일명은 `ViT-L-14.pt`이고 공식 URL에 들어 있는 예상 SHA256은 `b8cca3fd41ae0c99ba7e8951adf17d267cdb84cd88be6f7c2e0eca1737a03836`이다. URL은 검토 JSON에 보존했다. 후속 다운로드 후 `cache/clip/ViT-L-14.pt`의 실측 해시를 비교한다. **이번에는 모델 파일을 받지 않았으므로 실측 해시 검증은 하지 않았다.**

## 5. CUDA Toolkit 설치 명령 — 후속 단계 전용

**설치 전 남은 확인 명령(지금 실행하지 않음):** 이전 보고서를 덮어쓰지 않는 아래 preview를 먼저 수행한다. `success/dry_run`, LINK의 `(name, version, build_string)`118개, UNLINK0, prefix를 기존 보고서와 대조하고 일치할 때 실제 설치 단계로 간다. 버전/build 목록은 URL·artifact hash까지 고정한 Conda explicit lock은 아니므로 향후 repodata 변화가 있으면 재검토한다.

```bash
/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python -I -B -S \
  /home/minsujo/Desktop/SH/PHYSx/logs/install-plan-20260921/workspace_isolation.py \
  /bin/bash --noprofile --norc -seu -o pipefail <<'PHYSX_STAGE'
test ! -e "$PHYSX_CUDA"
test ! -L "$PHYSX_CUDA"
/home/minsujo/anaconda3/condabin/conda create --dry-run --json \
  --prefix "$PHYSX_CUDA" --override-channels --strict-channel-priority \
  --repodata-fn repodata.json --no-default-packages --copy --yes \
  -c https://conda.anaconda.org/nvidia/label/cuda-12.8.1 \
  -c https://repo.anaconda.com/pkgs/main \
  --file "$PHYSX_PLAN/cuda-toolkit.conda-specs.txt" \
  > "$PHYSX_PLAN/conda-final-isolated-preview.json" \
  2> "$PHYSX_PLAN/conda-final-isolated-preview.stderr.log"
PHYSX_STAGE
```

**실제 설치 명령(지금 실행하지 않음):**

이전 작업에서는 `cuda-toolkit=12.8.1`에 대한 **설치 미리보기만** 수행했다. 이번 재검토에서는 의존성 조회도 반복하지 않았다. Toolkit prefix는 아직 없다. 실제 설치 시에는 먼저 대상이 기존 환경이 아님을 확인하고, 아래의 118개 exact spec을 사용한다. 기존 폴더가 있으면 삭제하거나 덮어쓰지 않고 상태부터 확인한다.

```bash
/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python -I -B -S \
  /home/minsujo/Desktop/SH/PHYSx/logs/install-plan-20260921/workspace_isolation.py \
  /bin/bash --noprofile --norc -seu -o pipefail <<'PHYSX_STAGE'
exec >> "$PHYSX_PLAN/future-cuda-install.log" 2>&1
trap 'result=$?; printf "exit_code=%s\n" "$result"; exit "$result"' EXIT
date --iso-8601=seconds
test ! -e "$PHYSX_CUDA"
test ! -L "$PHYSX_CUDA"
/home/minsujo/anaconda3/condabin/conda create \
  --prefix "$PHYSX_CUDA" --override-channels --strict-channel-priority \
  --repodata-fn repodata.json --no-default-packages --copy --yes \
  -c https://conda.anaconda.org/nvidia/label/cuda-12.8.1 \
  -c https://repo.anaconda.com/pkgs/main \
  --file "$PHYSX_PLAN/cuda-toolkit.conda-specs.txt"
PHYSX_STAGE
```

시스템 driver 설치나 apt 작업은 하지 않는 계획이다. 선택한 Conda `cuda-toolkit` prefix에 포함되는 `cuda-driver-dev*`는 Toolkit 개발용 라이브러리/헤더이며 시스템 NVIDIA 커널 드라이버 설치를 뜻하지 않는다. prefix에 실제 `bin/nvcc`, 헤더, NVVM, cudart 라이브러리 및 링크가 생겼는지 확인하고, `nvcc --version` 결과가 12.8.93인지 확인한 후 다음 단계로 간다. 패키지 목록만으로 성공 판정하지 않는다. Toolkit conda 환경을 activate하여 compiler hook이 host 선택을 바꾸게 하지 않는다.

## 6. Python 패키지 설치와 미리보기 명령 — 후속 단계 전용

PyTorch 공식 조합은 torch2.7.1 / torchvision0.22.1 / cu128이다. 설치 대상은 항상 `$PHYSX_PYENV/bin/python -m pip`로 고정한다. `--user`, 환경 이름만 지정한 `conda -n`, 무버전 `pip install -U`, 공식 `setup.sh`의 일괄 실행은 사용하지 않는다.

**이전 의존성 조회의 근거:** 기존 pip 미리보기는 `install --dry-run --only-binary=:all: --report ...` 형태였다. source setup 실행은 피했지만 metadata 제공 방식에 따라 큰 wheel을 다운로드하기도 했다. 따라서 dry-run 성공은 설치 성공이 아니며, 다운로드량이 작다는 보장도 없다. 이번 재검토에서는 전체 pip 조회를 다시 실행하지 않았고 기존 보고서를 그대로 보존했다.

검증 결과: 최초 binary-only 미리보기는 **167개** 패키지를 해결하고 exit0으로 완료됐다. utils3d에 필요한 moderngl5.12.0 / plyfile1.1.2 / glcontext3.0.0 및 FlashAttention setup_requires의 psutil7.0.0은 기존 결과의 버전 제약 아래 별도 미리보기(exit0)로 확인했다. 두 결과의 중복을 합친 **171개**에 대해 현재 Python marker를 적용한 활성 기본 의존성 누락/버전 충돌은 0건이다. 선택적 extras 전체에 대한 검사는 아니며 런타임 성공 검증도 아니다. [검사 결과](python-metadata-validation.json).

실제 설치에 쓸 후보는 [python-foundation.lock.txt](python-foundation.lock.txt)의 **169개 wheel URL+SHA256**이다. spconv/cumm 2개는 [python-sparse-candidate.lock.txt](python-sparse-candidate.lock.txt)에 분리해 무조건 일괄 설치하는 기본 명령에서 제외했다. 전체 버전 제약은 [python-resolved.constraints.txt](python-resolved.constraints.txt)에 있다. 해시가 보고서에 없던 Jinja2/MarkupSafe 작은 wheel은 캐시로 받아 직접 SHA256을 계산했다. 이는 설치가 아니다.

아래 **실제 설치 명령은 지금 실행하지 않았다.** 위 격리 및 Toolkit 확인 이후 사용할 단계별 명령이다. 각 단계는 첫 실패에서 종료하고 공개 패키지 작업의 stdout/stderr·시각·종료 코드를 `logs/install-plan-20260921/future-*.log`에 남긴다. 직접 리다이렉션으로 로그를 열지 못하면 설치 전에 중단한다. 출력은 화면 대신 로그에 기록되므로 별도의 읽기 명령으로 확인한다. `set -x`나 환경변수 전체 출력은 쓰지 않는다.

```bash
/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python -I -B -S \
  /home/minsujo/Desktop/SH/PHYSx/logs/install-plan-20260921/workspace_isolation.py \
  /bin/bash --noprofile --norc -seu -o pipefail <<'PHYSX_STAGE'
exec >> "$PHYSX_PLAN/future-python-foundation.log" 2>&1
trap 'result=$?; printf "exit_code=%s\n" "$result"; exit "$result"' EXIT
date --iso-8601=seconds
"$PHYSX_PYENV/bin/python" -I -B -m pip --isolated --disable-pip-version-check \
  --cache-dir "$PIP_CACHE_DIR" install --only-binary=:all: --require-hashes \
  --index-url https://pypi.org/simple -r "$PHYSX_PLAN/python-foundation.lock.txt"
"$PHYSX_PYENV/bin/python" -I -B -m pip --isolated check
PHYSX_STAGE
```

spconv/cumm은 검토 후 해당 후보를 시험하기로 한 별도 단계에서만 다음 명령을 사용한다. 설치 완료와 RTX5090 연산 통과를 구분한다.

```bash
/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python -I -B -S \
  /home/minsujo/Desktop/SH/PHYSx/logs/install-plan-20260921/workspace_isolation.py \
  /bin/bash --noprofile --norc -seu -o pipefail <<'PHYSX_STAGE'
exec >> "$PHYSX_PLAN/future-python-sparse-candidate.log" 2>&1
trap 'result=$?; printf "exit_code=%s\n" "$result"; exit "$result"' EXIT
date --iso-8601=seconds
"$PHYSX_PYENV/bin/python" -I -B -m pip --isolated --cache-dir "$PIP_CACHE_DIR" \
  install --only-binary=:all: --require-hashes --index-url https://pypi.org/simple \
  -c "$PHYSX_PLAN/python-resolved.constraints.txt" \
  -r "$PHYSX_PLAN/python-sparse-candidate.lock.txt"
"$PHYSX_PYENV/bin/python" -I -B -m pip --isolated check
PHYSX_STAGE
```

FlashAttention/CLIP/utils3d/renderer/vox2seq 소스 빌드는 이 wheel 미리보기와 별도다. `pip check` 실패는 경고로 무시하지 않고 중단 조건으로 삼는다. Torch 버전이 설치 전후 2.7.1+cu128로 유지되는지 확인한다. utils3d 고정 소스의 실제 버전은0.0.2이며 pyproject.toml이 moderngl/numpy/plyfile/scipy와 setuptools>=61/wheel을 요구하는 것을 대조했다.

## 7. 소스 버전과 명령 — 빌드 미검증 후보

소스는 `sources/`의 새 디렉터리에만 확보한다. `git clone --no-checkout` 후 정확한 SHA를 checkout하는 아래 형태를 사용하고, 기존 디렉터리를 덮어쓰지 않는다.

```bash
/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python -I -B -S \
  /home/minsujo/Desktop/SH/PHYSx/logs/install-plan-20260921/workspace_isolation.py \
  /bin/bash --noprofile --norc -seu -o pipefail <<'PHYSX_STAGE'
exec >> "$PHYSX_PLAN/future-physx-flash-source.log" 2>&1
trap 'result=$?; printf "exit_code=%s\n" "$result"; exit "$result"' EXIT
date --iso-8601=seconds
test ! -e "$PHYSX_ROOT/sources/PhysX-3D"
test ! -L "$PHYSX_ROOT/sources/PhysX-3D"
git clone --no-checkout https://github.com/ziangcao0312/PhysX-3D.git "$PHYSX_ROOT/sources/PhysX-3D"
git -C "$PHYSX_ROOT/sources/PhysX-3D" checkout --detach 4f54e750a309fe9cd9f20816916ecc0e8a9ae594

test ! -e "$PHYSX_ROOT/sources/flash-attention"
test ! -L "$PHYSX_ROOT/sources/flash-attention"
git clone --no-checkout https://github.com/Dao-AILab/flash-attention.git "$PHYSX_ROOT/sources/flash-attention"
git -C "$PHYSX_ROOT/sources/flash-attention" checkout --detach 060c9188beec3a8b62b33a3bfa6d5d2d44975fab
git -C "$PHYSX_ROOT/sources/flash-attention" submodule update --init --recursive
FLASH_ATTENTION_FORCE_BUILD=TRUE FLASH_ATTN_CUDA_ARCHS=120 \
  "$PHYSX_PYENV/bin/python" -I -B -m pip --isolated --cache-dir "$PIP_CACHE_DIR" \
  install --no-build-isolation --no-deps -c "$PHYSX_PLAN/python-resolved.constraints.txt" \
  "$PHYSX_ROOT/sources/flash-attention"
"$PHYSX_PYENV/bin/python" -I -B -m pip --isolated check
PHYSX_STAGE
```

FlashAttention의 일반 `pip install`은 캐시된 CUDA12 wheel을 자동 선택할 수 있어 위 후보는 강제로 소스 빌드한다. `--no-build-isolation`은 미리 고정한 torch 및 빌드 도구를 사용하기 위한 것이며 ABI 호환 성공을 뜻하지 않는다. `--no-deps`로 source 설치 과정의 추가 의존성 선택/변경을 막고, 누락이 있으면 `pip check` 또는 빌드 오류에서 중단하여 pin을 다시 검토한다. sm120 빌드 flag/API 확인과 실제 dense/varlen forward 통과는 구분한다.

나머지 소스도 동일한 clone/checkout 방식으로 다음 SHA를 사용한다. 이 표의 버전은 현재 자료에 없던 무버전 설치를 고정한 **새 검토 후보**이며 실제 빌드로 검증된 값은 아니다.

| 로컬 폴더 / 공식 저장소 | SHA / 설치 대상 |
|---|---|
| `CLIP` / `openai/CLIP` | `d05afc436d78f1c48dc0dbf8e5980a9d471f35f6` / 저장소 루트 |
| `utils3d` / `EasternJournalist/utils3d` | `9a4eb15e4021b67b12c460c7057d642626897ec8` / 저장소 루트 |
| `nvdiffrast` / `NVlabs/nvdiffrast` | `729261dc64c4241ea36efda84fbf532cc8b425b8` (v0.3.3) / 저장소 루트 |
| `diffoctreerast` / `JeffreyXiang/diffoctreerast` | `b09c20b84ec3aace4729e6e18a613112320eca3a` / 저장소 루트 |
| `mip-splatting` / `autonomousvision/mip-splatting` | `dda02ab5ecf45d6edb8c540d9bb65c7e451345a9` / `submodules/diff-gaussian-rasterization` |
| `PhysX-3D/vox2seq` | 위 PhysX 고정 SHA의 **루트** `vox2seq`; `extensions/vox2seq`가 아님 |

```bash
/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python -I -B -S \
  /home/minsujo/Desktop/SH/PHYSx/logs/install-plan-20260921/workspace_isolation.py \
  /bin/bash --noprofile --norc -seu -o pipefail <<'PHYSX_STAGE'
exec >> "$PHYSX_PLAN/future-remaining-sources.log" 2>&1
trap 'result=$?; printf "exit_code=%s\n" "$result"; exit "$result"' EXIT
date --iso-8601=seconds
test ! -e "$PHYSX_ROOT/sources/CLIP"
test ! -L "$PHYSX_ROOT/sources/CLIP"
git clone --no-checkout https://github.com/openai/CLIP.git "$PHYSX_ROOT/sources/CLIP"
git -C "$PHYSX_ROOT/sources/CLIP" checkout --detach d05afc436d78f1c48dc0dbf8e5980a9d471f35f6
test ! -e "$PHYSX_ROOT/sources/utils3d"
test ! -L "$PHYSX_ROOT/sources/utils3d"
git clone --no-checkout https://github.com/EasternJournalist/utils3d.git "$PHYSX_ROOT/sources/utils3d"
git -C "$PHYSX_ROOT/sources/utils3d" checkout --detach 9a4eb15e4021b67b12c460c7057d642626897ec8
test ! -e "$PHYSX_ROOT/sources/nvdiffrast"
test ! -L "$PHYSX_ROOT/sources/nvdiffrast"
git clone --no-checkout https://github.com/NVlabs/nvdiffrast.git "$PHYSX_ROOT/sources/nvdiffrast"
git -C "$PHYSX_ROOT/sources/nvdiffrast" checkout --detach 729261dc64c4241ea36efda84fbf532cc8b425b8
test ! -e "$PHYSX_ROOT/sources/diffoctreerast"
test ! -L "$PHYSX_ROOT/sources/diffoctreerast"
git clone --no-checkout https://github.com/JeffreyXiang/diffoctreerast.git "$PHYSX_ROOT/sources/diffoctreerast"
git -C "$PHYSX_ROOT/sources/diffoctreerast" checkout --detach b09c20b84ec3aace4729e6e18a613112320eca3a
git -C "$PHYSX_ROOT/sources/diffoctreerast" submodule update --init --recursive
test ! -e "$PHYSX_ROOT/sources/mip-splatting"
test ! -L "$PHYSX_ROOT/sources/mip-splatting"
git clone --no-checkout https://github.com/autonomousvision/mip-splatting.git "$PHYSX_ROOT/sources/mip-splatting"
git -C "$PHYSX_ROOT/sources/mip-splatting" checkout --detach dda02ab5ecf45d6edb8c540d9bb65c7e451345a9

for source_path in \
  "$PHYSX_ROOT/sources/CLIP" \
  "$PHYSX_ROOT/sources/utils3d" \
  "$PHYSX_ROOT/sources/nvdiffrast" \
  "$PHYSX_ROOT/sources/diffoctreerast" \
  "$PHYSX_ROOT/sources/mip-splatting/submodules/diff-gaussian-rasterization" \
  "$PHYSX_ROOT/sources/PhysX-3D/vox2seq"; do
  "$PHYSX_PYENV/bin/python" -I -B -m pip --isolated --cache-dir "$PIP_CACHE_DIR" \
    install --no-build-isolation --no-deps -c "$PHYSX_PLAN/python-resolved.constraints.txt" "$source_path"
  "$PHYSX_PYENV/bin/python" -I -B -m pip --isolated check
done
PHYSX_STAGE
```

실제로는 각 source build의 stdout/stderr·시작/종료 시각·exit code를 별도 로그로 보존하고 첫 실패에서 중단한다. 고정 소스를 수정해야 하면 원본과 수정본을 구분하고 diff/hash를 기록한다. `diffoctreerast`의 GLM submodule SHA는 `33b4a621a697a305bc3a7610d290677b96beb181`이다. mip-splatting의 해당 rasterizer 디렉터리는 이 부모 SHA에 포함된 소스이다.

## 8. 진행 시점별 미해결 문제와 확인 기준

| 시점 | 해야 할 일 | 지금 상태 / 중단 조건 |
|---|---|---|
| **설치 시작 전** | 5절 새 명령과 동일한 격리·exact spec·`--no-default-packages --copy`로 Conda dry-run을 한 번 수행하고 기존 118개 버전/build 및 대상 prefix와 대조 | **아직 미실행.** 이전 solver 성공은 새 격리 조건의 성공 증거가 아님. 변경된 패키지·추가 pin 충돌은 설치 전 해결 |
| **설치 시작 전** | Python3.10.21/현재 4개 배포판·32개 Conda 기록, 빈 Toolkit 대상, 외부 symlink, 여유 공간 및 작업 로그 경로를 재확인 | 이번 보존 검사 결과는 별도 JSON. 기존 대상이 있거나 달라졌으면 삭제·덮어쓰기 없이 상태 확인 |
| **설치 시작 전** | 격리 실행기 기동과 캐시 경로 확인, 외부 환경 보존 | 최소 경로 검사는 통과. 향후 실행에서 namespace/권한 오류가 나면 보호 설정을 바꾸거나 격리를 생략하지 않음 |
| **Toolkit 설치 직후 / 확장 빌드 전** | 실제 nvcc12.8.93·헤더·NVVM·cudart와 링크 대상 확인, 절대경로 GCC/G++13.3 재확인 | 미설치이므로 미확인. Conda의 HOME 등록 경고, 설치 exit code, 실제 파일을 함께 확인 |
| **Python 기본 설치 직후** | 지정 환경 배포판/버전을 lock과 비교하고 `pip check`; torch/torchvision/Kaolin 버전 유지, 외부 prefix 변경 없음 확인 | 미설치. metadata 조회 통과만으로 대신할 수 없음. JIT/모델 초기화를 부르는 import는 아직 하지 않음 |
| **각 source 빌드 직후** | 실제 NVCC/host compiler 명령·arch·빌드 로그·산출물 경로, `pip check` 확인 | 모든 source 빌드 미검증. 오류를 무시하거나 `--allow-unsupported-compiler`로 우회하지 않음 |
| **첫 모델 다운로드/CLIP 실행 전** | CLIP 두 호출에 검토 패치 적용/정적 검색, HF/Torch/rembg 경로와 revision 확인 | 검토용 diff만 작성. 작업 소스에 패치 적용·실제 가중치 다운로드는 아직 안 함 |
| **별도 GPU 실행 단계** | FlashAttention dense/varlen, spconv sparse conv, Kaolin mesh, vox2seq, 두 rasterizer 및 nvdiffrast 각각 최소 연산 검증 | 전부 미실행. import나 설치 성공은 GPU 연산 통과가 아님 |

spconv-cu1262.3.8은 cumm-cu126>=0.7.11,<0.8.0을 요구한다. cumm0.7.11의 arch 목록은9.0까지이며 `CUMM_CUDA_ARCH_LIST=12.0`을 강제하면 Unknown CUDA arch가 발생한다. wheel의 PTX/NVRTC 경로가 RTX5090에서 통과하는지는 미확인이다. cumm0.8.2 강제 교체는 이 제약과 충돌한다. 기본169개 wheel/Toolkit 준비를 이 후보의 GPU 호환성 확정으로 표현하지 않으며, sparse2개는 별도 시험 후보로 유지한다.

기존 통합 계획의 관절/GT 패치, split 중복 정책, 9지표 평가 연결 문제는 환경 준비와 별도다. 환경 설치 완료만으로 논문 수치 재현이 완료되는 것은 아니다.

## 9. 모델 다운로드는 환경 검증 이후

모델 revision은 통합 계획을 유지한다. 모델 본체는 이번에 다운로드하지 않았다. 후속 다운로드는 위 HF cache 설정 하에서 아래처럼 고정한다.

```bash
/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python -I -B -S \
  /home/minsujo/Desktop/SH/PHYSx/logs/install-plan-20260921/workspace_isolation.py \
  /bin/bash --noprofile --norc -seu -o pipefail <<'PHYSX_STAGE'
exec >> "$PHYSX_PLAN/future-hf-model-download.log" 2>&1
trap 'result=$?; printf "exit_code=%s\n" "$result"; exit "$result"' EXIT
date --iso-8601=seconds
"$PHYSX_PYENV/bin/hf" download microsoft/TRELLIS-image-large \
  --revision 25e0d31ffbebe4b5a97464dd851910efc3002d96 \
  --local-dir "$PHYSX_ROOT/sources/PhysX-3D/pretrain/trellis"
"$PHYSX_PYENV/bin/hf" download Caoza/PhysXGen \
  --revision 52598097b7092df495ac149e137050ce2d2784fe \
  --local-dir "$PHYSX_ROOT/sources/PhysX-3D/pretrain"
PHYSX_STAGE
```

통합 계획의 두 저장소 합계 약15.8GB는 전체 설치 공간이 아니다. Conda dry-run의 신규 FETCH 예상량은 2,100,106,977 bytes(약2.10GB), 118개 LINK 계획이며 unpacked 설치 크기와 다르다. PyTorch runtime/wheel 캐시, 빌드, 추가 모델, 출력 공간도 필요하다. 기존 여유 약494GiB를 참고하되 설치 직전 다시 확인한다. 큰 데이터/XL과 GPU 실험은 이 계획 작성 범위에 포함하지 않는다.

## 10. 근거와 증거

- 로컬 기준: `repro-records/04_PhysX-3D/PhysX-3D_팀원비교_통합실행계획.md`, 환경 구축 보고서, 검토용 01~03 스크립트. 기록 저장소 commit `57024349614adb6f846a7a988b59a4ff1e0c9bd8`.
- [공식 PyTorch 과거 버전](https://pytorch.org/get-started/previous-versions/)
- [CUDA 12.8.1 release notes](https://docs.nvidia.com/cuda/archive/12.8.1/cuda-toolkit-release-notes/index.html)
- [NVIDIA Conda 설치 및 label](https://docs.nvidia.com/cuda/archive/12.8.1/cuda-installation-guide-linux/index.html#conda-installation)
- [고정 PhysX setup.sh](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/setup.sh), 로컬 읽기용 사본 [upstream-setup.review.txt](upstream-setup.review.txt).
- [Kaolin 공식 wheel index](https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.7.1_cu128.html)
- [FlashAttention 2.8.3 setup.py](https://github.com/Dao-AILab/flash-attention/blob/v2.8.3/setup.py)
- [spconv 지원표](https://github.com/traveller59/spconv#prebuilt-gpu-support-matrix), [cumm0.7.11 arch 검사](https://github.com/FindDefinition/cumm/blob/v0.7.11/cumm/common.py)
- [OpenAI CLIP 다운로드 기본 경로](https://github.com/openai/CLIP/blob/d05afc436d78f1c48dc0dbf8e5980a9d471f35f6/clip/clip.py), [Transformers4.51.3 캐시 우선순위](https://github.com/huggingface/transformers/blob/v4.51.3/src/transformers/utils/hub.py), [Hub0.34.4 캐시 변수](https://github.com/huggingface/huggingface_hub/blob/v0.34.4/src/huggingface_hub/constants.py).
- [이번 최종 검증](isolation-review-verification.json), [이번 산출물 SHA256](isolation-review-sha256.json).
- [Conda dry-run 원본 JSON](conda-cuda128-dry-run.json), [PyPI 후보 metadata](pypi-candidate-metadata.json), [소스 SHA manifest](source-pins.json).

현재 증거는 문서/소스/패키지 메타데이터, 이전 의존성 미리보기, 이번에 수행한 제한적인 격리 경로 검사이다. 실제 설치 완료, compiler 성공, GPU 호환 완료라는 판정을 내리지 않는다.
