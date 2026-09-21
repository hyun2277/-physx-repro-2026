# PhysX-3D 작업 폴더 전용 설치 계획

작성일: 2026-09-21 (Asia/Seoul). **계획 및 설치 미리보기이며 실제 설치·컴파일·GPU 실험은 하지 않았다.** 아래 설치 명령은 후속 단계에서 검토하여 사용할 명령이다. 이 문서를 통째로 실행하는 자동 설치 스크립트로 취급하지 않는다.

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

**외부 쓰기를 막기 위한 후속 설치 조건:** 현재 Conda23.3.1은 실제 create 때 `~/.conda/environments.txt`에 환경 경로를 등록한다. 캐시/prefix 변수만으로 이 등록 경로가 바뀌지 않으며 해당 버전에는 `CONDA_REGISTER_ENVS` 같은 해제 옵션도 없다. 따라서 실제 설치는 아래처럼 PHYSx만 쓰기 가능한 일회성 프로세스 격리 안에서 수행하는 안으로 정했다. HOME을 바꾸지 않는다. `/usr/bin/bwrap` 파일 존재는 확인했지만 이번에는 격리 실행을 시험하지 않았으므로, **설치 전 격리 기동 및 읽기 전용 외부 경로 검증이 선행 조건**이다. 동작하지 않으면 격리를 제거하고 설치를 강행하지 않는다. Conda 등록 파일의 쓰기 거부는 해당 버전 소스에서 경고로 처리되지만 실제 전체 설치 성공은 아직 미검증이다.

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

## 4. 후속 작업용 셸과 캐시 경로 — 지금은 실행하지 않음

아래 환경변수는 작업용 자식 셸 안에서만 사용한다. 셸 초기화 파일이나 전역 Conda 설정에 추가하지 않는다. `HOME`을 바꾸지 않는다. 캐시 폴더 생성은 후속 설치 준비 시 수행한다.

```bash
set -euo pipefail
export PHYSX_ROOT=/home/minsujo/Desktop/SH/PHYSx
mkdir -p "$PHYSX_ROOT/tmp"
/usr/bin/bwrap --die-with-parent --unshare-pid \
  --ro-bind / / --bind "$PHYSX_ROOT" "$PHYSX_ROOT" \
  --bind "$PHYSX_ROOT/tmp" /tmp --bind "$PHYSX_ROOT/tmp" /var/tmp \
  --proc /proc --dev /dev --chdir "$PHYSX_ROOT" \
  /bin/bash --noprofile --norc
```

격리 셸이 성공적으로 열린 것을 확인한 뒤 **그 셸 안에서** 다음 환경 블록과 후속 명령을 실행한다. bwrap 기동 실패 시 원래 셸에서 설치 명령으로 이어가지 않는다.

```bash
set -euo pipefail
export PHYSX_ROOT=/home/minsujo/Desktop/SH/PHYSx
export PHYSX_PYENV="$PHYSX_ROOT/envs/physxgen"
export PHYSX_CUDA="$PHYSX_ROOT/toolchains/cuda-12.8.1"
export PHYSX_PLAN="$PHYSX_ROOT/logs/install-plan-20260921"
export CONDA_PKGS_DIRS="$PHYSX_ROOT/cache/conda"
export CONDA_ENVS_PATH="$PHYSX_ROOT/envs"
export CONDARC="$PHYSX_PLAN/preview.condarc"
export CONDA_AUTO_UPDATE_CONDA=false CONDA_NOTIFY_OUTDATED_CONDA=false
export CONDA_REPORT_ERRORS=false
export PIP_CACHE_DIR="$PHYSX_ROOT/cache/pip"
export PIP_CONFIG_FILE=/dev/null
export XDG_CACHE_HOME="$PHYSX_ROOT/cache/xdg"
export TMPDIR="$PHYSX_ROOT/tmp" TMP="$PHYSX_ROOT/tmp" TEMP="$PHYSX_ROOT/tmp"
export TORCH_HOME="$PHYSX_ROOT/cache/torch"
export TORCH_EXTENSIONS_DIR="$PHYSX_ROOT/build/torch-extensions"
export HF_HOME="$PHYSX_ROOT/cache/huggingface"
export HF_HUB_CACHE="$HF_HOME/hub" HF_ASSETS_CACHE="$HF_HOME/assets"
export HF_XET_CACHE="$HF_HOME/xet"
export U2NET_HOME="$PHYSX_ROOT/cache/u2net"
export CUDA_CACHE_PATH="$PHYSX_ROOT/cache/cuda"
export TRITON_CACHE_DIR="$PHYSX_ROOT/cache/triton"
export NUMBA_CACHE_DIR="$PHYSX_ROOT/cache/numba"
export MPLCONFIGDIR="$PHYSX_ROOT/cache/matplotlib"
export IMAGEIO_USERDIR="$PHYSX_ROOT/cache/imageio"
export PYTHONPYCACHEPREFIX="$PHYSX_ROOT/cache/pycache"
export PYTHONNOUSERSITE=1
export CUDA_HOME="$PHYSX_CUDA"
export CUDACXX="$PHYSX_CUDA/bin/nvcc"
export CC=/usr/bin/gcc-13 CXX=/usr/bin/g++-13
export CUDAHOSTCXX="$CXX" NVCC_CCBIN="$CXX"
export PATH="$PHYSX_PYENV/bin:$PHYSX_CUDA/bin:/usr/bin:/bin"
export TORCH_CUDA_ARCH_LIST=12.0
export MAX_JOBS=4
unset LD_LIBRARY_PATH LD_PRELOAD PYTHONPATH CUMM_CUDA_ARCH_LIST
mkdir -p "$CONDA_PKGS_DIRS" "$PIP_CACHE_DIR" "$XDG_CACHE_HOME" "$TMPDIR" \
  "$TORCH_HOME" "$TORCH_EXTENSIONS_DIR" "$HF_HUB_CACHE" "$HF_ASSETS_CACHE" \
  "$HF_XET_CACHE" "$U2NET_HOME" "$CUDA_CACHE_PATH" "$TRITON_CACHE_DIR" \
  "$NUMBA_CACHE_DIR" "$MPLCONFIGDIR" "$IMAGEIO_USERDIR" "$PYTHONPYCACHEPREFIX" \
  "$PHYSX_ROOT/cache/clip" "$PHYSX_ROOT/sources" "$PHYSX_ROOT/outputs"
```

위 격리안의 `/dev`에는 GPU 장치를 제공하지 않는다. 이는 설치/소스 빌드 단계용이며 이후 GPU 검증용 실행 방식과 구분한다. `/tmp`, `/var/tmp`를 사용한 파일도 실제로는 PHYSx/tmp에 저장된다. 환경 설정은 격리 셸 안에서만 유효하며 시스템 보호 설정이나 원래 HOME 경로를 수정하지 않는다.

`pip --isolated`는 PIP 계열 환경변수를 무시할 수 있어 아래에서는 `--cache-dir`를 명시한다. nvdiffrast 0.3.3은 JIT 내부에서 `TORCH_CUDA_ARCH_LIST`를 덮어쓰므로 이 변수만으로 모든 확장의 타깃이 고정됐다고 판단하지 않는다.

**확인된 추가 캐시 보완:** 고정 PhysX 소스 `example.py:153`과 `dataset_toolkits/merge_property.py:51`은 OpenAI `clip.load`에 `download_root`를 넘기지 않는다. 기본값은 XDG를 읽지 않고 `~/.cache/clip`을 사용하므로, 후속 작업용 소스에서 두 호출에 `download_root="/home/minsujo/Desktop/SH/PHYSx/cache/clip"`을 명시하고 diff를 보존해야 한다. 이번에는 수정하지 않았다. 한편 pipeline의 Transformers `CLIPTextModel.from_pretrained`는 HF 캐시 경로를 사용한다.

spconv2.3.8/cumm0.7.11에는 `CUMM_CACHE_PATH`, `SPCONV_CACHE_PATH`, XDG 캐시 변수를 읽는 구현이 없으므로 그런 변수를 만들어 해결됐다고 주장하지 않는다. 해당 버전 NVRTC 재사용은 메모리 dict이며, editable JIT 산출물은 각 패키지의 `PACKAGE_ROOT/core_cc`에 생성된다. 환경과 소스를 PHYSx 아래 두어 이를 수용한다. NVIDIA 드라이버 PTX 디스크 캐시는 별도의 `CUDA_CACHE_PATH`, Python tempfile 경로는 `TMPDIR`로 지정한다.

## 5. CUDA Toolkit 설치 명령 — 후속 단계 전용

현재 작업 중에는 아래 명령의 **`--dry-run` 형태만** 사용했다. Toolkit prefix는 아직 없다. 실제 설치 시에는 먼저 대상이 기존 환경이 아님을 확인하고, 아래의 118개 exact spec을 사용한다. 기존 폴더가 있으면 삭제하거나 덮어쓰지 않고 상태부터 확인한다.

```bash
test ! -e "$PHYSX_CUDA"
/home/minsujo/anaconda3/condabin/conda create \
  --prefix "$PHYSX_CUDA" --override-channels --strict-channel-priority \
  --repodata-fn repodata.json \
  -c https://conda.anaconda.org/nvidia/label/cuda-12.8.1 \
  -c https://repo.anaconda.com/pkgs/main \
  --file "$PHYSX_PLAN/cuda-toolkit.conda-specs.txt"
```

시스템 driver 설치나 apt 작업은 하지 않는 계획이다. 선택한 Conda `cuda-toolkit` prefix에 포함되는 `cuda-driver-dev*`는 Toolkit 개발용 라이브러리/헤더이며 시스템 NVIDIA 커널 드라이버 설치를 뜻하지 않는다. prefix에 실제 `bin/nvcc`, 헤더, NVVM, cudart 라이브러리 및 링크가 생겼는지 확인하고, `nvcc --version` 결과가 12.8.93인지 확인한 후 다음 단계로 간다. 패키지 목록만으로 성공 판정하지 않는다. Toolkit conda 환경을 activate하여 compiler hook이 host 선택을 바꾸게 하지 않는다.

## 6. Python 패키지 설치와 미리보기 명령 — 후속 단계 전용

PyTorch 공식 조합은 torch2.7.1 / torchvision0.22.1 / cu128이다. 설치 대상은 항상 `$PHYSX_PYENV/bin/python -m pip`로 고정한다. `--user`, 환경 이름만 지정한 `conda -n`, 무버전 `pip install -U`, 공식 `setup.sh`의 일괄 실행은 사용하지 않는다.

아래는 이 작업에서 사용하는 **설치 미리보기** 형태다. `--only-binary=:all:`로 소스 빌드/패키지 setup 실행을 막는다. wheel의 metadata를 받기 위해 일부 wheel 전체가 캐시에 다운로드될 수 있으며, 그것은 환경에 설치된 상태와 다르다.

```bash
"$PHYSX_PYENV/bin/python" -I -B -m pip \
  --isolated --disable-pip-version-check --cache-dir "$PIP_CACHE_DIR" \
  install --dry-run --only-binary=:all: \
  --report "$PHYSX_PLAN/pip-dry-run-report.json" \
  --index-url https://pypi.org/simple \
  --extra-index-url https://download.pytorch.org/whl/cu128 \
  --find-links https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.7.1_cu128.html \
  -r "$PHYSX_PLAN/python-direct-candidates.txt"
```

검증 결과: 최초 binary-only 미리보기는 **167개** 패키지를 해결하고 exit0으로 완료됐다. utils3d에 필요한 moderngl5.12.0 / plyfile1.1.2 / glcontext3.0.0 및 FlashAttention setup_requires의 psutil7.0.0은 기존 결과의 버전 제약 아래 별도 미리보기(exit0)로 확인했다. 두 결과의 중복을 합친 **171개**에 대해 현재 Python marker를 적용한 활성 기본 의존성 누락/버전 충돌은 0건이다. 선택적 extras 전체에 대한 검사는 아니며 런타임 성공 검증도 아니다. [검사 결과](python-metadata-validation.json).

실제 설치에 쓸 후보는 [python-foundation.lock.txt](python-foundation.lock.txt)의 **169개 wheel URL+SHA256**이다. spconv/cumm 2개는 [python-sparse-candidate.lock.txt](python-sparse-candidate.lock.txt)에 분리해 무조건 일괄 설치하는 기본 명령에서 제외했다. 전체 버전 제약은 [python-resolved.constraints.txt](python-resolved.constraints.txt)에 있다. 해시가 보고서에 없던 Jinja2/MarkupSafe 작은 wheel은 캐시로 받아 직접 SHA256을 계산했다. 이는 설치가 아니다.

아래 **실제 설치 명령은 지금 실행하지 않았다.** 위 격리 및 Toolkit 확인 이후 사용할 단계별 명령이다.

```bash
"$PHYSX_PYENV/bin/python" -m pip --isolated --disable-pip-version-check \
  --cache-dir "$PIP_CACHE_DIR" install --only-binary=:all: --require-hashes \
  --index-url https://pypi.org/simple -r "$PHYSX_PLAN/python-foundation.lock.txt"
"$PHYSX_PYENV/bin/python" -m pip --isolated check
```

spconv/cumm은 검토 후 해당 후보를 시험하기로 한 별도 단계에서만 다음 명령을 사용한다. 설치 완료와 RTX5090 연산 통과를 구분한다.

```bash
"$PHYSX_PYENV/bin/python" -m pip --isolated --cache-dir "$PIP_CACHE_DIR" \
  install --only-binary=:all: --require-hashes --index-url https://pypi.org/simple \
  -c "$PHYSX_PLAN/python-resolved.constraints.txt" \
  -r "$PHYSX_PLAN/python-sparse-candidate.lock.txt"
"$PHYSX_PYENV/bin/python" -m pip --isolated check
```

FlashAttention/CLIP/utils3d/renderer/vox2seq 소스 빌드는 이 wheel 미리보기와 별도다. `pip check` 실패는 경고로 무시하지 않고 중단 조건으로 삼는다. Torch 버전이 설치 전후 2.7.1+cu128로 유지되는지 확인한다. utils3d 고정 소스의 실제 버전은0.0.2이며 pyproject.toml이 moderngl/numpy/plyfile/scipy와 setuptools>=61/wheel을 요구하는 것을 대조했다.

## 7. 소스 버전과 명령 — 빌드 미검증 후보

소스는 `sources/`의 새 디렉터리에만 확보한다. `git clone --no-checkout` 후 정확한 SHA를 checkout하는 아래 형태를 사용하고, 기존 디렉터리를 덮어쓰지 않는다.

```bash
git clone --no-checkout https://github.com/ziangcao0312/PhysX-3D.git "$PHYSX_ROOT/sources/PhysX-3D"
git -C "$PHYSX_ROOT/sources/PhysX-3D" checkout --detach 4f54e750a309fe9cd9f20816916ecc0e8a9ae594

git clone --no-checkout https://github.com/Dao-AILab/flash-attention.git "$PHYSX_ROOT/sources/flash-attention"
git -C "$PHYSX_ROOT/sources/flash-attention" checkout --detach 060c9188beec3a8b62b33a3bfa6d5d2d44975fab
git -C "$PHYSX_ROOT/sources/flash-attention" submodule update --init --recursive
FLASH_ATTENTION_FORCE_BUILD=TRUE FLASH_ATTN_CUDA_ARCHS=120 \
  "$PHYSX_PYENV/bin/python" -m pip --isolated --cache-dir "$PIP_CACHE_DIR" \
  install --no-build-isolation -c "$PHYSX_PLAN/python-resolved.constraints.txt" \
  "$PHYSX_ROOT/sources/flash-attention"
```

FlashAttention의 일반 `pip install`은 캐시된 CUDA12 wheel을 자동 선택할 수 있어 위 후보는 강제로 소스 빌드한다. `--no-build-isolation`은 미리 고정한 torch 및 빌드 도구를 사용하기 위한 것이며 ABI 호환 성공을 뜻하지 않는다. sm120 빌드 flag/API 확인과 실제 dense/varlen forward 통과는 구분한다.

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
git clone --no-checkout https://github.com/openai/CLIP.git "$PHYSX_ROOT/sources/CLIP"
git -C "$PHYSX_ROOT/sources/CLIP" checkout --detach d05afc436d78f1c48dc0dbf8e5980a9d471f35f6
git clone --no-checkout https://github.com/EasternJournalist/utils3d.git "$PHYSX_ROOT/sources/utils3d"
git -C "$PHYSX_ROOT/sources/utils3d" checkout --detach 9a4eb15e4021b67b12c460c7057d642626897ec8
git clone --no-checkout https://github.com/NVlabs/nvdiffrast.git "$PHYSX_ROOT/sources/nvdiffrast"
git -C "$PHYSX_ROOT/sources/nvdiffrast" checkout --detach 729261dc64c4241ea36efda84fbf532cc8b425b8
git clone --no-checkout https://github.com/JeffreyXiang/diffoctreerast.git "$PHYSX_ROOT/sources/diffoctreerast"
git -C "$PHYSX_ROOT/sources/diffoctreerast" checkout --detach b09c20b84ec3aace4729e6e18a613112320eca3a
git -C "$PHYSX_ROOT/sources/diffoctreerast" submodule update --init --recursive
git clone --no-checkout https://github.com/autonomousvision/mip-splatting.git "$PHYSX_ROOT/sources/mip-splatting"
git -C "$PHYSX_ROOT/sources/mip-splatting" checkout --detach dda02ab5ecf45d6edb8c540d9bb65c7e451345a9

for source_path in \
  "$PHYSX_ROOT/sources/CLIP" \
  "$PHYSX_ROOT/sources/utils3d" \
  "$PHYSX_ROOT/sources/nvdiffrast" \
  "$PHYSX_ROOT/sources/diffoctreerast" \
  "$PHYSX_ROOT/sources/mip-splatting/submodules/diff-gaussian-rasterization" \
  "$PHYSX_ROOT/sources/PhysX-3D/vox2seq"; do
  "$PHYSX_PYENV/bin/python" -m pip --isolated --cache-dir "$PIP_CACHE_DIR" \
    install --no-build-isolation -c "$PHYSX_PLAN/python-resolved.constraints.txt" "$source_path"
  "$PHYSX_PYENV/bin/python" -m pip --isolated check
done
```

실제로는 각 source build의 stdout/stderr·시작/종료 시각·exit code를 별도 로그로 보존하고 첫 실패에서 중단한다. 고정 소스를 수정해야 하면 원본과 수정본을 구분하고 diff/hash를 기록한다. `diffoctreerast`의 GLM submodule SHA는 `33b4a621a697a305bc3a7610d290677b96beb181`이다. mip-splatting의 해당 rasterizer 디렉터리는 이 부모 SHA에 포함된 소스이다.

## 8. 설치 후에도 남는 검증과 진행 조건

- **spconv는 확정 호환 조합이 아니다.** spconv-cu126 2.3.8은 cumm-cu126>=0.7.11,<0.8.0을 요구한다. cumm0.7.11의 지원 arch 목록은 9.0까지이고, `CUMM_CUDA_ARCH_LIST=12.0`을 강제로 지정하면 Unknown CUDA arch가 난다. wheel의 PTX/NVRTC 경로가 5090에서 통과하는지는 아직 알 수 없다. 단순히 최신 cumm0.8.2를 강제 설치하는 것은 의존성 충돌이다.
- FlashAttention dense 및 varlen, spconv sparse conv, Kaolin mesh 연산, vox2seq, 두 rasterizer 및 nvdiffrast JIT를 각각 검증해야 한다. import 성공은 통과 조건이 아니다. 이러한 GPU/컴파일 검증은 이번 작업에서 실행하지 않았다.
- CUDA Toolkit 설치 후 실제 nvcc/헤더/라이브러리 경로 및 최종 compiler command를 확인해야 한다. 전용 prefix가 있다는 사실만으로 모든 빌드가 그 Toolkit을 사용한다고 단정하지 않는다.
- 캐시 경로를 따르지 않는 CLIP/cumm 등의 코드가 있으면 작업용 소스/환경 안에서 명시적 경로를 전달하는 보완을 먼저 설계한다. 시스템 HOME/캐시를 바꾸거나 다른 연구 환경을 수정하지 않는다.
- 관절/GT 패치, split 중복 정책 및 9지표 평가 연결은 통합 계획의 미해결 항목으로 유지한다. 환경 설치 성공은 이 항목들의 해결이나 논문 수치 재현을 뜻하지 않는다.

## 9. 모델 다운로드는 환경 검증 이후

모델 revision은 통합 계획을 유지한다. 모델 본체는 이번에 다운로드하지 않았다. 후속 다운로드는 위 HF cache 설정 하에서 아래처럼 고정한다.

```bash
"$PHYSX_PYENV/bin/hf" download microsoft/TRELLIS-image-large \
  --revision 25e0d31ffbebe4b5a97464dd851910efc3002d96 \
  --local-dir "$PHYSX_ROOT/sources/PhysX-3D/pretrain/trellis"
"$PHYSX_PYENV/bin/hf" download Caoza/PhysXGen \
  --revision 52598097b7092df495ac149e137050ce2d2784fe \
  --local-dir "$PHYSX_ROOT/sources/PhysX-3D/pretrain"
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
- [Conda dry-run 원본 JSON](conda-cuda128-dry-run.json), [PyPI 후보 metadata](pypi-candidate-metadata.json), [소스 SHA manifest](source-pins.json).

현재 증거는 문서/소스/패키지 메타데이터와 설치 미리보기 수준이다. 실제 설치 완료, compiler 성공, GPU 호환 완료라는 판정을 내리지 않는다.
