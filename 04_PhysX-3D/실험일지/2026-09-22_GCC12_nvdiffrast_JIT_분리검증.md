# GCC 12 host compiler 가설 분리 검증

## 범위

원본 `example.py`, 모델 추론, GPU context 생성 없이 `nvdiffrast` CUDA 확장만 JIT 빌드했다. 새 패키지 설치·다운로드·시스템 CUDA·원본 소스·pretrain·모델·데이터 수정은 하지 않았다.

- 실행 스크립트: `04_PhysX-3D/실행스크립트/run_nvdiffrast_gcc12_compile.sh`
- 결과 로그: `/home/minsujo/Desktop/SH/PHYSx/logs/nvdiffrast-gcc12/20260922T072351Z/`
- 종료 코드: `0`

## 실제 compiler 선택

빌드 프로세스에 다음 변수를 명시했다.

```text
CC=/usr/bin/gcc-12
CXX=/usr/bin/g++-12
CUDAHOSTCXX=/usr/bin/g++-12
NVCC_CCBIN=/usr/bin/g++-12
```

`environment.log`에서 실제 경로는 다음으로 확인된다.

```text
gcc_resolved=/usr/bin/x86_64-linux-gnu-gcc-12
g++_resolved=/usr/bin/x86_64-linux-gnu-g++-12
gcc-12 (Ubuntu 12.4.0-2ubuntu1~24.04.1) 12.4.0
g++-12 (Ubuntu 12.4.0-2ubuntu1~24.04.1) 12.4.0
```

실제 `build.stdout.log`의 CUDA 명령에는 `-ccbin /usr/bin/gcc-12`가 포함되어 있고, C++ 단계는 `/usr/bin/g++-12`를 직접 호출했다. CUDA compiler는 CUDA 12.8.1 overlay의 `nvcc`이며 버전은 `V12.8.93`이다.

## 결과

15개 소스로 `nvdiffrast_plugin_gcc12_probe`를 빌드·로드했고, `build.stdout.log` 마지막에 다음이 기록됐다.

```text
nvdiffrast JIT compile and load completed
```

이번 GCC 12 빌드의 `build.stderr.log`와 `build.stdout.log`에는 이전 실패의 `_Float32`, `_Float64`, `_Float128`, `_Float32x`, `_Float64x` 오류가 없다. 따라서 GCC 12를 명시한 host compilation에서는 해당 `_Float32` 오류가 재현되지 않았고, GCC 12 선택은 문제를 분리하는 유효한 다음 설정으로 확인됐다.

`CUDA_VISIBLE_DEVICES`는 빈 값으로 설정했고, 스크립트는 `nvdiffrast`의 JIT loader만 호출했다. `example.py`나 renderer의 CUDA context 생성, 모델 추론은 호출하지 않았다. `TORCH_EXTENSIONS_DIR`와 CUDA overlay, 임시 build 산출물은 위 run 폴더 아래에만 생성했다.

## 판정

GCC 12.4.0을 명시한 최소 JIT 빌드가 성공했으므로, 세 번째 원본 실행에서 기본 host compiler 조합으로 발생한 `_Float32` 오류는 GCC 12 선택으로 사라졌다. 이것은 GCC 13.3.0과 CUDA 12.8.1/Ubuntu 헤더 조합이 원인일 가능성을 높이지만, GCC 13 단독 원인이라고 확정하는 비교 실험은 아니다.

원본 table 예제는 아직 재실행하지 않았으므로 완료 상태가 아니다. 다음 조치는 원본 실행 스크립트에 GCC 12를 적용할지 검토하는 것이며, 적용 전에는 기존 보호·로그 규칙을 유지해야 한다.
