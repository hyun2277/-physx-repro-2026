# 원본 공식 table 예제 세 번째 실행 실패 조사

## 조사 범위

- 실행 로그: `/home/minsujo/Desktop/SH/PHYSx/logs/original-example-terminal/20260922T071314Z/`
- 조사일: 2026-09-22
- 이번 조사에서는 설치·다운로드, GPU 실행, PyTorch CUDA 연산, `example.py` 재실행, 원본 소스 수정을 하지 않았다.

## 로그에서 확인한 사실

`example.exit_code.txt`는 `1`이고 `ABORT_REASON.txt`는 `example_failed_exit_code=1`이다. 실패는 원본 `example.py`의 렌더링 단계에서 `nvdiffrast_plugin` JIT 확장을 빌드할 때 발생했다.

로그에 남은 첫 컴파일 명령은 다음과 같다.

```text
c++ -MMD ... -isystem /home/minsujo/Desktop/SH/PHYSx/logs/original-example-terminal/20260922T071314Z/cuda-home/include ... -std=c++17 ...
/home/minsujo/Desktop/SH/PHYSx/logs/original-example-terminal/20260922T071314Z/cuda-home/bin/nvcc --generate-dependencies-with-compile ... -gencode=arch=compute_120,code=compute_120 -gencode=arch=compute_120,code=sm_120 ... -std=c++17 ...
```

`example.command.txt`의 실행 환경은 위 run 폴더의 CUDA overlay를 `CUDA_HOME`, `CUDACXX`, `PATH`에 지정하고, `PATH`의 일반 `/usr/bin`을 그대로 포함한다. 명령에는 `nvcc -ccbin` 또는 `CUDAHOSTCXX`가 명시되어 있지 않다.

`preflight_nvcc_version.stdout.log`의 버전은 다음과 같다.

```text
Cuda compilation tools, release 12.8, V12.8.93
```

overlay의 `nvcc`는 `/home/minsujo/Desktop/SH/PHYSx/toolchains/cuda-12.8.1/bin/nvcc`를 가리킨다. 따라서 compute_120/sm_120 선택과 target include의 `cuda_runtime_api.h` 탐색은 이 실패에서 이미 진행된 상태다.

실패한 CUDA 단계는 `RasterImpl.cu` 컴파일이며, Ubuntu 시스템 헤더에서 다음 오류가 발생했다.

```text
/usr/include/stdlib.h: identifier "_Float32" is undefined
/usr/include/stdlib.h: identifier "_Float64" is undefined
/usr/include/stdlib.h: identifier "_Float128" is undefined
/usr/include/x86_64-linux-gnu/bits/mathcalls.h: identifier "_Float32" is undefined
```

즉 이번 로그에서 확정되는 실패 층은 CUDA host compilation과 Ubuntu 24.04 계열 시스템 헤더의 조합이다. 로그만으로 GCC 13.3.0 자체가 원인이라고 확정할 수는 없다.

## 현재 설치된 host compiler 후보

다음 후보는 모두 파일이 존재하고 버전 명령이 성공하는 것으로 읽기 전용 확인했다.

| 명령 | 실제 대상 | 버전 |
|---|---|---|
| `/usr/bin/gcc`, `/usr/bin/g++`, `/usr/bin/c++` | GCC/G++ 13 | 13.3.0 (`13.3.0-6ubuntu2~24.04.1`) |
| `/usr/bin/gcc-13`, `/usr/bin/g++-13` | GCC/G++ 13 | 13.3.0 (`13.3.0-6ubuntu2~24.04.1`) |
| `/usr/bin/gcc-12`, `/usr/bin/g++-12` | GCC/G++ 12 | 12.4.0 (`12.4.0-2ubuntu1~24.04.1`) |
| `gcc-14`, `g++-14` | 없음 | 사용할 수 없음 |

현재 로그의 C++ 명령은 `c++`를 사용하고 CUDA 명령에 `-ccbin`이 없으므로, 실제 host compiler가 PATH의 기본 GCC 13이었다는 것은 강한 정황이지만 로그에 compiler 경로를 직접 출력한 사실은 아니다. 기존 작업 격리 기록은 `/usr/bin/gcc-13`, `/usr/bin/g++-13`, `CUDAHOSTCXX=/usr/bin/g++-13`, `NVCC_CCBIN=/usr/bin/g++-13`을 명시하도록 계획했다.

## 공식 근거와 판정

- [CUDA 12.8.1 NVCC Compiler Driver](https://docs.nvidia.com/cuda/archive/12.8.1/pdf/CUDA_Compiler_Driver_NVCC.pdf)는 host compiler가 필요하며, 별도 지정이 없으면 PATH의 기본 `gcc`/`g++`를 사용하고 `-ccbin` 등으로 지정할 수 있다고 설명한다.
- [CUDA 12.8.1 Linux Installation Guide](https://docs.nvidia.com/cuda/archive/12.8.1/pdf/CUDA_Installation_Guide_Linux.pdf)는 Linux host compiler와 C++ dialect 요구사항을 설명한다.
- [CUDA 12.8.1 Release Notes](https://docs.nvidia.com/cuda/archive/12.8.1/cuda-toolkit-release-notes/index.html)는 Ubuntu 24.04에서 NVCC와 GCC 조합의 컴파일 문제를 수정한 항목과 Blackwell SM_120 지원을 기록한다.
- 작업 폴더의 기존 환경 기록은 Ubuntu 24.04.3 LTS, GCC/G++ 13.3.0, CUDA 12.8 계열을 기록하고, host compiler를 절대 경로로 고정하도록 계획한다.

따라서 “CUDA 12.8.1이 Ubuntu 24.04와 호환되지 않는다” 또는 “GCC 13.3.0만의 버그다”라고 결론 낼 근거는 부족하다. 현재 확인 가능한 판정은 다음과 같다.

1. **이미 있는 compiler 선택:** GCC/G++ 12.4.0과 13.3.0이 모두 설치되어 있다. 추가 설치 없이 `nvcc`에 host compiler를 명시할 수 있다.
2. **작업 폴더 전용 추가 설치 필요:** 현재 증거만으로는 필요성이 확인되지 않았다. 새 패키지 설치를 정당화할 기록은 없다.
3. **미확정:** 기본 PATH의 GCC 13.3.0과 CUDA 12.8.1 nvcc가 Ubuntu 24.04 `mathcalls.h`의 `_Float32*` 선언을 처리하는 정확한 상호작용은 아직 분리되지 않았다.

## 다음 한 단계

전체 예제를 다시 실행하기 전에, 이미 설치된 `/usr/bin/gcc-12`와 `/usr/bin/g++-12`를 `nvcc -ccbin`/동등한 host compiler 설정으로 명시한 **최소 host-only nvdiffrast CUDA 컴파일**을 한 번 수행한다. 이 단계는 GCC 13 기본 선택과의 차이만 분리하며, 결과가 같으면 GCC 선택만으로는 원인을 설명할 수 없다는 것을 확인한다. 설치·다운로드·시스템 CUDA 변경·원본 소스 변경·전체 `example.py` 재실행은 그 결과가 나온 뒤에도 별도로 승인하고 진행해야 한다.

이번 세 번째 실행도 원본 table 예제를 완료하지 못했으며, 최종 출력물은 생성되지 않았다.
