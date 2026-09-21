# 고정 sparse wheel 정적 검토 — 2026-09-21

이 기록의 범위는 고정 URL 두 개의 다운로드, SHA256 대조, ZIP/METADATA 및 ELF/PTX 정적 검사다. 이 검토 과정에서는 패키지 설치·import·소스 빌드·GPU/NVRTC 연산을 하지 않았다. 이후 주 작업자의 설치·실행 결과는 `../official-example-20260921/`에 별도로 기록된다. 아래 설치 전 패키지 수는 이 정적 검토 당시의 상태다.

## 다운로드와 보존

| 배포판 | 버전 | wheel bytes | SHA256 |
| --- | --- | ---: | --- |
| cumm-cu126 | 0.7.11 | 26,584,327 | `97a07c38b45d552952a12fd16f7f570f35b108e88068ed86386686bbbadaa59c` |
| spconv-cu126 | 2.3.8 | 70,476,017 | `16f3744cd697e225b1d6a9f37fd2a4aed7bd6b89dd4c431af5a76c39fda0ab38` |

두 파일은 `../../cache/sparse-wheels/`에 보관했다. [고정 URL 목록](locked-artifacts.json)의 값은 기존 `../install-plan-20260921/python-sparse-candidate.lock.txt`와 일치한다. 실제 METADATA의 이름·버전·요구 의존성도 기존 pip 초기 보고서와 같았다. 두 wheel 모두 `.pth`, `sitecustomize.py`, `usercustomize.py`가 없다. [메타데이터 비교](dependency-metadata-comparison.json)와 [보존 검사](preservation.json)에 근거해 정적 검토 전후 기존 Python 배포판 170개의 버전은 변하지 않았다.

최초 sandbox 호출은 bwrap namespace 생성 권한 오류로 exit 1이었다. 같은 검토 launcher의 승인된 재호출은 기존 bwrap 파일시스템 격리 아래에서 exit 0으로 완료했다. 보호 설정은 변경하지 않았다. 각 호출과 `curl`, `readelf`, `cuobjdump`의 명령·stdout·stderr·exit code는 별도 파일에 남겼다. Device code가 없는 ELF에 대한 `cuobjdump --list-ptx`/`--list-elf`의 exit 255와 `does not contain device code`는 예상된 분류 결과로 보존했다.

## 실제 ELF와 PTX

`cumm/core_cc...so`의 RPATH는 `$ORIGIN/../cumm_cu126.libs`다. DT_NEEDED에는 해시가 포함된 `libcudart-53d54daa.so.12.6.68`, `libnvrtc-a1f1e7d6.so.12.6.85`, `libnvrtc-builtins-a1d5fce3.so.12.6.85`가 있으며, 해당 파일들이 wheel 안에 실제 존재한다. `spconv/core_cc...so`는 `$ORIGIN/../spconv_cu126.libs` RPATH와 동일한 cudart 12.6.68 파일을 포함한다. 두 cudart 파일의 바이트와 SHA256은 같다. Toolkit 12.8의 PATH/CUDA_HOME만 설정해도 이 의존성이 NVRTC 12.8로 교체되는 것은 아니다. RPATH 패치나 LD_PRELOAD는 하지 않았다.

spconv core에는 PTX 모듈 606개(sm_52 195개, sm_90 411개), cubin 모듈 3,471개가 있다. cubin 구성은 sm_50 133, sm_52 328, sm_60 411, sm_61 133, sm_70/75/80/86/89/90 각각 411개다. 전체 PTX dump에서 `.version 8.5`, `.target sm_52` 및 `.target sm_90`만 확인했으며 `.entry` 행은 1,242개다. sm_90a와 sm_120은 없다. PTX 전체 출력은 gzip으로 보관했으며 [ELF 요약](spconv-cu126.elf-summary.json)에 목록과 집계를 남겼다.

일반 PTX가 있다는 사실은 Blackwell에서 driver PTX JIT 경로를 시험할 근거다. 특정 입력의 수치 정확성, 모든 kernel/shape의 호환성을 입증하지는 않는다. 실제 wheel의 `cumm/nvrtc/__init__.py`는 GPU compute capability로 `--gpu-architecture=sm_<major><minor>`를 구성한다. SM120에서 이 fallback을 타면, bundled NVRTC 12.6이 해당 아키텍처를 지원하지 않는 문제가 남는다. [NVRTC 12.6 문서](https://docs.nvidia.com/cuda/archive/12.6.3/nvrtc/index.html#supported-compile-options), [Blackwell 호환성 문서](https://docs.nvidia.com/cuda/archive/12.8.1/blackwell-compatibility-guide/index.html)를 참고한다.

## 실행 단계에 전달할 조건

기존 기본 GPU launcher는 Toolkit 경로를 제외하므로 sparse/nvdiffrast 확장 검사에는 확장용 profile이 필요하다. 확장 검사에서는 작업 폴더의 Toolkit 12.8.1 경로와 headers를 명시하되 runtime loader를 강제로 바꾸지 말고 `/proc/self/maps`의 NVRTC·cudart·libcuda 실제 경로 및 이미 로드된 NVRTC의 버전을 기록한다. `CUMM_DISABLE_JIT=1`, `SPCONV_DISABLE_JIT=1`은 editable source extension 빌드를 끄는 용도이고 driver PTX JIT/NVRTC 실행 금지를 뜻하지 않는다.

최소 수치 검사는 8×4 FP32 feature, 5×5×5 격자, 3×3×3 SubMConv3d, bias 없음, TF32 끔으로 구성한다. Native와 자동 선택 알고리즘을 각각 한 번 forward하고, 좌표를 정렬하여 CPU float64 dense conv3d 기준과 비교한다(atol 1e-5, rtol 1e-4). 첫 실패에 중단하며 traceback·실제 mapped libraries·GPU 사용량을 남긴다. 한 번의 forward도 내부 autotuning으로 여러 kernel을 실행할 수 있다. 이 문서는 그 실행 결과를 주장하지 않는다.

재검토 시 [기계 판독 요약](result.json), [파일 해시 목록](artifacts-sha256.json)을 먼저 확인한다. 다운로드·추출 script는 기존 파일 보존을 전제로 하므로 현재 설치 환경에서 재실행용 설치 명령으로 사용하지 않는다.
