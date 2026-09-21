# 2026-09-21 — 미설치 확장의 버전·빌드·최소 검사 계획

**계획 검토만 수행했다. 설치·빌드·패키지 import·모델 다운로드·GPU 실행은 하지 않았다.** 기준 commit은 `a244a00fd5c69b869d9d88b82e5c8b09e50bdfc1`이다. 다음 명령/검사는 별도 단계 승인 후 사용할 설계이며 이 문서를 통째로 실행하지 않는다.

## 1. 재사용한 근거와 현재 기준

[통합 실행계획](../../PhysX-3D_팀원비교_통합실행계획.md), [최신 로컬 설치 계획의 보존본](../2026-09-21_자료보완/local-records/logs/install-plan-20260921/installation-plan.md), [source-pins.json](../2026-09-21_자료보완/local-records/logs/install-plan-20260921/source-pins.json), [기본 패키지 설치 일지](../../실험일지/2026-09-21_기본Python패키지_설치.md), [기본 GPU 검사 성공](../../실험일지/2026-09-21_기본PyTorch_GPU검사.md)을 재사용했다. 기존 버전 후보·컴파일러 지원표·모델 revision을 다시 조회하거나 변경하지 않았다.

이번에는 설치 환경의 **dist-info metadata만** 읽어 계획 기준과 차이를 확인했다. [결과](installed-metadata.json)는 170개 배포판이 기존 설치 기록과 모두 같고, 아래 미설치 대상이 여전히 없음을 보여 준다. `pip check`나 GPU 검사를 반복 실행한 것은 아니다. 현재 `sources/`는 비어 있어 실제 빌드용 checkout은 아직 없다.

| 유지할 항목 | 기준 |
| --- | --- |
| 작업 루트 | `/home/minsujo/Desktop/SH/PHYSx` (`PHYSx`) |
| 지정 Python | `envs/physxgen`, Python 3.10.21 |
| torch / torchvision | **2.7.1+cu128 / 0.22.1+cu128**, 기본 GPU 연산 1회 통과 |
| Toolkit / NVCC | `toolchains/cuda-12.8.1` / **12.8.93**, 기존 설치·실제 파일 검사 유지 |
| host compiler | `/usr/bin/gcc-13`, `/usr/bin/g++-13`, **13.3.0**; 시스템 기본 링크 변경 없음 |
| build 도구 | setuptools 75.8.0, wheel 0.45.1, packaging 24.2, ninja 1.11.1.4, cmake 3.31.6, build 1.2.2.post1, psutil 7.0.0 |
| C++ ABI 근거 | 설치된 TorchConfig.cmake의 `TORCH_CXX_FLAGS`는 `_GLIBCXX_USE_CXX11_ABI=1`; 실제 빌드에서는 PyTorch 제공 값을 사용하고 임의 반전하지 않음 |

170개 배포판 유지·기본 torch 성공은 아래 확장들의 ABI/SM120/GPU 연산 성공을 뜻하지 않는다. 원본 설치 계획의 “미설치”는 작성 당시 상태다.

## 2. 꼭 필요한 것과 선택 가능한 것

기준은 **고정 PhysX 소스를 바꾸지 않은 공식 example의 mesh 동영상 + Gaussian/mesh GLB 생성 경로**다. 파일에 import가 적혀 있는 것과 실제 선택 분기에서 필요한 것은 구분했다. [근거와 추가 조사 범위](review-findings.md)를 함께 읽는다.

| 항목 | 분류 / 필요 이유 | 정확한 버전·소스 | 설치 방식 |
| --- | --- | --- | --- |
| spconv + cumm | **필수**, 기본 sparse convolution backend | `spconv-cu126==2.3.8`, `cumm-cu126==0.7.11`; 기존 URL/SHA lock 유지 | 고정 wheel 두 개만. 내부 PTX/NVRTC를 먼저 확인하는 시험 후보 |
| FlashAttention | **필수**, 선택한 dense+sparse attention 경로 | 2.8.3 / `060c9188beec3a8b62b33a3bfa6d5d2d44975fab` | SM120 소스 wheel 빌드. xformers 동시 설치 불필요 |
| vox2seq | **조건부**, serialized attention을 실제 선택할 때. 고정 checkpoint의 attn_mode 전체 대조 전 필수 여부 보류 | PhysX `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`의 **루트 `vox2seq/`** | 필요 조건 확인 후 고정 하위 소스 wheel 빌드; `extensions/vox2seq` 사용 금지 |
| nvdiffrast | **필수**, mesh renderer 및 관련 import 경로 | 0.3.3 / `729261dc64c4241ea36efda84fbf532cc8b425b8` | Python 패키지 설치 후 첫 CUDA context에서 JIT 빌드 |
| diff-gaussian-rasterization | **필수**, 공식 example의 Gaussian/mesh GLB 생성에서 Gaussian 렌더 사용 | mip-splatting `dda02ab5ecf45d6edb8c540d9bb65c7e451345a9`의 `submodules/diff-gaussian-rasterization` | 이 고정 디렉터리의 CUDA wheel 빌드; 다른 동명 배포판으로 교체 금지 |
| Kaolin | **필수지만 이미 설치됨**, mesh 표현/FlexiCubes의 import 경로 | 기존 torch2.7.1/cu128용 **0.18.0** | 재설치 제외. 별도 최소 CUDA 연산 검사만 남음 |
| OpenAI CLIP | **필수 보조 Python 패키지**, example의 텍스트/속성 경로 | `d05afc436d78f1c48dc0dbf8e5980a9d471f35f6` | 고정 소스 wheel. CUDA 확장 빌드가 아니며 가중치는 별도 |
| utils3d | **필수 보조 Python 패키지**, 카메라/mesh 유틸리티 | 0.0.2 / `9a4eb15e4021b67b12c460c7057d642626897ec8` | 고정 소스 wheel. 기본 의존성은 이미 설치됨 |
| diffoctreerast | **조건부 선택**, octree/radiance-field 렌더링을 실제 사용할 때 | `b09c20b84ec3aace4729e6e18a613112320eca3a`; GLM `33b4a621a697a305bc3a7610d290677b96beb181` | 별도 CUDA wheel 빌드. 현재 example 기본 출력에는 우선 설치하지 않음 |
| xformers | **대체 선택**, FlashAttention 경로를 교체하기로 결정한 경우만 | 이번 계획에서는 새 후보 없음, 미설치 유지 | torch2.7.1/cu128에 맞는 후보·ABI·sparse API를 별도 검토한 뒤 설치법 확정 |

`ATTN_BACKEND=sdpa`만 설정해 FlashAttention과 xformers를 모두 생략하는 방안은 채택하지 않는다. 기존 통합 계획에서 확인한 sparse backend 제약이 남아 있다. **기존 일괄 설치 후보였던 vox2seq와 diffoctreerast는 고정 소스의 실제 호출 분기를 확인해 조건부로 분리했다.** 필요한 경로를 사용할 때 생략해도 된다는 뜻은 아니다. source 기본 decoder의 `swin`, flow의 `full`과 실제 checkpoint 설정이 항상 같다고 가정하지 않는다. 학습·웹 demo 전용 패키지, 다른 renderer/attention 최신판과 모델 다운로드는 이번 기본 설치 목록에서 제외한다.

## 3. 실행 순서와 중단 기준

| 순서 | 후속 단계 | 통과해야 다음으로 진행 |
| --- | --- | --- |
| 설치/GPU 전 | 아래 확장 전용 실행 조건을 반영한 실행기와 시험 입력 준비 | 기본 GPU 실행기를 임의 명령용으로 바꾸지 않음. 코드·출력 경로·GPU/빌드 허용 범위 검토. 다음 1번의 다운로드/정적 검토는 기존 설치용 격리+개별 로그로 먼저 가능 |
| 1 | **spconv/cumm 고정 wheel 확보 → SHA/METADATA/ELF/PTX 조사** | 실제 두 파일이 lock과 일치, 추가 의존성/torch 변경 없음, 라이브러리 선택 위험 정리 |
| 2 | 승인된 두 wheel만 설치 → sparse 최소 수치 검사 | SM120/PTX/NVRTC 경로가 미확인이므로 먼저 작은 시험. 실패하면 중단, 자동 업그레이드 금지 |
| 3 | PhysX와 CLIP/utils3d 및 필요한 source checkout을 고정 → 보조 Python wheel 설치 | 소스·submodule SHA, CPU import/metadata, pip check; CLIP 가중치 호출 없음 |
| 4 | FlashAttention SM120 wheel 빌드·설치 → 실제 사용 dense/varlen API 검사 | 단순 import만으로 통과 처리하지 않음 |
| 5 | Gaussian rasterizer 빌드·설치·단일 primitive 검사 | PhysX의 카메라/settings 규약 및 유한한 출력 확인 |
| 6 | nvdiffrast 패키지 설치 → **승인된 단일 GPU JIT 빌드+검사**, 기존 Kaolin 최소 연산 검사 | 첫 JIT와 runtime을 분리 기록. 모델·OpenGL context 불필요 |
| 조건부 | 고정 checkpoint에 serialized attention이 있으면 vox2seq 빌드·설치·encode/decode 검사 | 해당 모델 경로를 호출하기 전에 완료. 불필요한 경우 NVCC 시험만을 위해 설치하지 않음 |
| 선택 | 실제 octree 출력이 필요해질 때 diffoctreerast 빌드·trivec 검사 | 해당 출력이 필요한 이유와 입력/API 확정. 기본 경로 성공과 별도 판정 |

서로 다른 패키지를 한 pip 명령이나 일괄 shell loop로 설치하지 않는다. 단계마다 현재 배포판·소스·빌드 옵션을 기록하고 변경 예정 집합과 대조한다. 첫 실패에서 해당 단계 로그를 보존하고 멈춘다. 일부 단계 성공을 전체 pipeline 성공으로 바꾸지 않는다.

## 4. 설치/빌드 명령의 공통 형식 — 아직 실행하지 않음

빌드용으로는 기존 [workspace_isolation.py](../2026-09-21_자료보완/local-records/logs/install-plan-20260921/workspace_isolation.py)의 외부 읽기 전용·PHYSx 쓰기·GPU 숨김 원칙을 유지한다. source/submodule 확보와 wheel 빌드를 구분하고, 확보 후 빌드·설치는 네트워크 차단 profile에서 처리하도록 준비한다. 기존 실행기는 네트워크를 차단하지 않으므로 **오프라인 build profile 보완·검토는 후속 구현 조건**이다. 현재 기본 GPU 실행기는 지정 torch smoke만 실행하므로 다른 검사를 그대로 전달할 수 없다.

아래는 각 격리 profile **안에서 실행할 자식 명령의 형식**이다. `$PHYSX_SRC`, `$PHYSX_STAGE_WHEELS`, `$PHYSX_REVIEWED_WHEEL_LOCK`은 아래 표의 단일 대상으로 확정한 후 사용한다. 실행별 stdout/stderr·시작/종료·실제 exit를 수집하는 runner에 연결하기 전에는 복사 실행하지 않는다.

```bash
# 자식 환경 안에서만 지정. 원래 셸/시스템 설정은 변경하지 않음.
export CUDA_HOME=/home/minsujo/Desktop/SH/PHYSx/toolchains/cuda-12.8.1
export CUDACXX="$CUDA_HOME/bin/nvcc"
export CC=/usr/bin/gcc-13 CXX=/usr/bin/g++-13
export CUDAHOSTCXX=/usr/bin/g++-13 NVCC_CCBIN=/usr/bin/g++-13
export TORCH_CUDA_ARCH_LIST=12.0 MAX_JOBS=2 NVCC_THREADS=1
# clean allowlist에서 구성. 기존 LD_LIBRARY_PATH/LD_PRELOAD를 이어받지 않음.
export PATH="$CUDA_HOME/bin:/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin:/usr/bin:/bin"

# 단일 source로 wheel 생성: source backend 실행/컴파일을 포함하는 실제 빌드 단계임.
/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python -I -B -S \
  /home/minsujo/Desktop/SH/PHYSx/logs/python-foundation-install-20260921/pip_without_site.py \
  --isolated --cache-dir /home/minsujo/Desktop/SH/PHYSx/cache/pip \
  wheel --no-index --no-build-isolation --no-deps \
  --wheel-dir "$PHYSX_STAGE_WHEELS" "$PHYSX_SRC"

# 생성 wheel의 이름/버전/소스/metadata와 실측SHA 검토 후, 단일 file:// URL+hash lock 작성.
# 두 sparse wheel은 별도 2개 lock. 아직 존재하지 않는 wheel hash를 미리 지어내지 않음.
/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python -I -B -S \
  /home/minsujo/Desktop/SH/PHYSx/logs/python-foundation-install-20260921/pip_without_site.py \
  --isolated --cache-dir /home/minsujo/Desktop/SH/PHYSx/cache/pip \
  install --no-index --no-deps --no-compile --only-binary=:all: --require-hashes \
  -r "$PHYSX_REVIEWED_WHEEL_LOCK"
```

설치 직전 같은 로컬 lock으로 `install --dry-run --report <PHYSx/logs/run_id/report.json>`을 먼저 수행해 대상/버전 변경을 대조한다. 실제 설치 후에는 지정 Python의 `pip_without_site.py --isolated check`와 dist-info 비교를 수행한다. torch/torchvision 및 기존 170개가 의도 없이 바뀌면 중단한다. `--no-deps`나 pip check 통과는 C++ ABI·GPU kernel 호환 보장이 아니다.

| 패키지별 차이 | 소스 위치 / 별도 지정 |
| --- | --- |
| CLIP / utils3d | `PHYSx/sources/CLIP`, `PHYSx/sources/utils3d`; 각각 표의 SHA에서 wheel 하나씩 생성 |
| vox2seq | `PHYSx/sources/PhysX-3D/vox2seq`; 루트 PhysX SHA 확인 |
| FlashAttention | `PHYSx/sources/flash-attention`; submodule 고정 확인, wheel 명령에 **`FLASH_ATTENTION_FORCE_BUILD=TRUE FLASH_ATTN_CUDA_ARCHS=120`** 추가 |
| nvdiffrast | `PHYSx/sources/nvdiffrast`; wheel 설치 완료를 CUDA plugin 빌드 완료로 기록하지 않음 |
| Gaussian rasterizer | `PHYSx/sources/mip-splatting/submodules/diff-gaussian-rasterization`; 부모 SHA와 해당 디렉터리 기록 |
| diffoctreerast | `PHYSx/sources/diffoctreerast`; 고정 GLM submodule 포함 |
| spconv/cumm | 소스 빌드 대신 [기존 sparse 후보 lock](../2026-09-21_자료보완/local-records/logs/install-plan-20260921/python-sparse-candidate.lock.txt)의 정확한 wheel 두 개 사용 |

소스 확보는 새 경로에 `git clone --no-checkout <표의 공식 URL>` → `git checkout --detach <고정SHA>` → 해당 revision의 `submodule update --init --recursive` 순서다. 기존 경로가 있으면 덮어쓰지 않고 HEAD·diff·submodule 상태부터 확인한다. 공식 URL은 기존 source-pins에 있으며 `setup.sh`를 실행하거나 source하지 않는다. 원본 pin은 그대로 두고 필요한 patch는 별도 diff/hash로 검토한다.

## 5. 패키지별 최소 동작 검사 설계

**이 표는 아직 구현·실행하지 않은 검사 계약이다.** 모든 GPU 검사는 당시 idle GPU를 다시 선택하고 UUID/minor를 대조한다. GPU 번호 1이 계속 비어 있다고 가정하지 않는다. GPU1의 과거 기본 matmul 성공은 재사용하되 다시 matmul부터 반복하지 않는다. 각 검사에는 timeout, 입력/seed, synchronize, 실제 stdout/stderr/exit, GPU 사용량·로드 라이브러리 경로를 기록한다.

| 대상 | 모델 없는 최소 입력·호출 | 통과 기준 / 범위 |
| --- | --- | --- |
| spconv/cumm | FP32 `SparseConvTensor` + **`SubMConv3d(4,4,kernel_size=3,padding=1,bias=False)`**, batch1, 공간5³, 활성 좌표8개. eval/no-grad·TF32 off. 좌표 `[batch,z,y,x]` int32. 비대칭의 작은 고정 특징/가중치 | CPU dense conv3d의 활성 좌표 결과와 정렬 비교, finite·좌표집합 동일·`atol=1e-5,rtol=1e-4`. 1×1은 torch.mm으로 빠질 수 있어 제외. 최초 forward 내부 autotuning/JIT 가능. backward/FP16/전체모델 미검증 |
| FlashAttention | Q/K=0, 작은 결정적 V; FP16 dense `[1,16,2,64]`, varlen 두 길이8(누적길이 CUDA int32 `[0,8,16]`). `flash_attn_func`와 `flash_attn_varlen_func`로 시작하고 실제 callsite의 packed 변형도 검사 | 결과가 각 sequence V 평균과 일치·shape/finite·동기화 성공. FP16 `atol=2e-3,rtol=2e-3`을 초기 검사 기준으로 명시; BF16 사용 경로는 별도 dtype 검사. 임의 random 긴 입력/학습 backward 통과로 확대하지 않음 |
| vox2seq | 작은 정수 좌표 집합으로 `encode(coords,permute=[0,1,2],mode='z_order')` → `decode(code,...)` 왕복. `hilbert`도 필요 경로별 검사. 실제 CUDA wrapper와 별도 `vox2seq.pytorch` 결과 비교 | 좌표 정확 복원·중복 없는 코드·범위/순서 확인. API에 backend/use_cuda/pure 인자는 없음. pure 모듈도 부모 `_C` import 때문에 미설치 fallback이 아님 |
| nvdiffrast | 단일 삼각형: CUDA float32 pos `[1,3,4]`, int32 tri `[1,3]`, 32×32. `RasterizeCudaContext(device='cuda:0')` → `rasterize` → `interpolate` | 이 단계에서 JIT 빌드 허용 필요. shape/finite·삼각형 내부 coverage 존재·상수 attribute 보존. OpenGL context·모델 다운로드 없이 수행 |
| Gaussian rasterizer | PhysX와 같은 카메라/행렬 규약의 단일 Gaussian, 16×16, precomputed RGB, 양의 opacity/scale, 단위 quaternion. `GaussianRasterizer(settings)` forward | color/radii shape/finite·양의 가시 radius·배경과 다른 덮임. `kernel_size`,`subpixel_offset` 포함 mip 버전 settings로 입력을 먼저 확정. 실제 장면/모델 의미 검증과 구분 |
| Kaolin(기설치) | CUDA FP32 작은 점군 `[1,4,3]`; `kaolin.metrics.pointcloud.sided_distance(p,p)` 또는 `chamfer_distance(p,p)` | 거리0·finite·CUDA동기화; 실제 `_C.metrics.sided_distance_forward_cuda` 호출. 단순 torch 기반 유틸만 호출해 Kaolin native 성공이라고 하지 않음. PhysX FlexiCubes 전체경로 미검증 |
| CLIP(보조) | CPU `import clip`, `clip.tokenize(['test'])` | 토큰 shape `[1,77]`와 package/source 위치 확인. **clip.load/from_pretrained 호출 금지**; 가중치/모델검사 아님 |
| utils3d(보조) | 고정 소스의 package metadata와 CPU import 확인 | 버전0.0.2/소스 위치 일치. 카메라·mesh 실제 연산은 nvdiffrast/renderer 연계 검사에서 별도 확인 |
| diffoctreerast(선택) | PhysX의 실제 **Strivec/trivec** 경로와 `OctreeRenderer` 설정을 이용한 극소 장면 forward | optional 실행 전 primitive·tensor shape·카메라 입력 고정 필요. 기본 voxel settings만 임의 구성해 전체 renderer 호환성을 판정하지 않음 |
| xformers(대체 선택) | 후보를 별도 확정한 뒤 실제 dense/sparse 호출 signature·dtype로 비교 | 지금 검사/설치 명령을 확정하지 않음. FlashAttention 실패 시 즉시 자동 설치하는 fallback 아님 |

spconv 참조 가중치 배치는 `[out,kz,ky,kx,in]`이다. CPU dense conv3d 참조는 `[out,in,kz,ky,kx]`로 변환하고 active 좌표에서만 값을 꺼낸다. 최소 좌표 예시는 `(0,0,0),(1,1,1),(1,1,2),(1,2,1),(2,1,1),(2,2,2),(3,3,3),(4,4,4)`이며 여기에 batch0을 붙인다. 이 작은 허용오차는 검사 설계값이지 논문 재현의 오차 기준이 아니다.

FlashAttention의 실제 호출은 dense `flash_attn_qkvpacked_func`/`flash_attn_kvpacked_func`/`flash_attn_func`, sparse full의 `flash_attn_varlen_qkvpacked_func`/`flash_attn_varlen_kvpacked_func`/`flash_attn_varlen_func`다. windowed/serialized도 qkvpacked와 varlen-qkvpacked를 사용한다. 같은 작은 입력을 packed 형태로 바꾼 수치 비교까지 해야 실제 사용 API 전체를 검사했다고 할 수 있다. 두 일반 함수만 통과하면 해당 두 API의 검사 결과로 한정한다.

## 6. 아직 풀어야 할 호환성·실행기 문제

1. **spconv/cumm SM120**: cumm0.7.11의 arch 목록은9.0까지이고 `CUMM_CUDA_ARCH_LIST=12.0` 강제는 해법이 아니다. 다만 PTX 호환 분기가 있으므로 wheel을 메타데이터만 보고 불가로 확정하지 않는다. NVRTC fallback은 장치에 맞춰 `sm_120`을 요구하며 NVRTC12.6으로는 문제가 예상된다. 실제 wheel의 PTX·`.libs`·`DT_NEEDED`·`RPATH/RUNPATH` 및 로드되는 NVRTC/builtins/cudart를 아직 확인하지 못했다. cumm0.8.2 강제 교체나 torch 업그레이드는 기존 제약을 깨므로 하지 않는다.
2. **sparse 런타임의 Toolkit 선택**: cumm은 Linux에서 `which nvcc`로 헤더 경로를 찾고 실패하면 `/usr/local/cuda`로 돌아갈 수 있다. 확장 검사 profile은 작업 Toolkit/bin을 PATH에 먼저 두고 `nvcc`, `lib/libcudart.so`, `targets/x86_64-linux/include/cuda.h` 실제 경로를 확인해야 한다. 이 파일들은 존재하지만 PATH나 CUDA_HOME만으로 wheel의 실제 NVRTC 선택까지 보장하지는 못한다. `CUMM_DISABLE_JIT`/`SPCONV_DISABLE_JIT`는 editable 빌드 차단과 NVRTC/PTX JIT 차단이 같은 뜻이 아니다.
3. **nvdiffrast 첫 호출은 빌드**: 고정 ops.py가 `TORCH_CUDA_ARCH_LIST=''`로 덮는다. 원본+GPU숨김 상태의 첫 JIT는 PyTorch의 빈 arch 목록 오류가 예상된다(소스 추론, 미실행). 원본을 유지하고 **선택 GPU를 노출한 offline JIT+검사 단계**로 설계한다. 숨김 사전 빌드로 바꾸려면 별도 patch 검토가 필요하며 지금 적용하지 않는다.
4. **기존 basic GPU 실행기의 한계**: 고정 matmul만 실행하고 CUDA_HOME/컴파일 설정을 제외하므로 확장/JIT 검사에 그대로 사용할 수 없다. 새 allowlist형 확장 검사 profile이 필요하다. UUID/minor·한 GPU·외부 RO·Python/Toolkit RO·네트워크 차단을 유지하되 필요한 compiler/arch/cache만 명시한다. site-packages 쓰기나 예상치 못한 download/JIT가 필요하면 실패로 기록하고 보호를 자동 완화하지 않는다.
5. **C++ 빌드/ABI 및 장면 검사 입력**: GCC13.3/NVCC12.8/torch2.7.1의 기존 근거를 유지하지만 개별 확장 빌드 성공은 미확인이다. 실제 compile command의 `-ccbin`, `sm_120`, ABI, 필요한 link 경로를 남긴다. mip renderer의 카메라·primitive 입력과 선택 octree smoke는 실행 전 작은 입력 fixture가 더 필요하다. vox2seq의 실제 필요 여부는 고정 checkpoint의 attn_mode 대조가 남아 있다. unsupported-compiler 옵션·ABI 강제 변경으로 통과시키지 않는다.
6. **CLIP 경로**: 기존 [CLIP patch](../2026-09-21_자료보완/local-records/logs/install-plan-20260921/clip-cache-path.review.patch)는 아직 미적용이다. 패키지 설치/CPU tokenize와 별개로 첫 모델 다운로드 전 두 `clip.load`에 `download_root`와 `PHYSx/cache/clip`을 적용·확인해야 한다. 환경 변수만 지정해서 완료했다고 하지 않는다.

## 7. 저장·기록·다음 한 단계

소스는 `PHYSx/sources`, 고정 wheel은 `PHYSx/cache/extension-wheels/<package>/<run_id>`, 빌드 산출물은 `PHYSx/build/extensions/<package>/<run_id>`, PyTorch JIT는 `PHYSx/build/torch-extensions`, tmp/shm은 `PHYSx/tmp`, CUDA cache는 `PHYSx/cache/cuda` 아래로 고정한다. 부모 환경·토큰·loader 설정을 상속하지 않으며 시스템 CUDA/driver/다른 환경은 그대로 둔다. HOME을 바꾸거나 writable로 확장하지 않는다.

각 download/build/install/check는 별도 실행 ID의 command·stdout·stderr·exit·환경/입력 해시를 기록하고, GPU 단계에만 사용량을 수집한다. 생성 wheel/큰 로그/산출물은 Git에 넣지 않고 위치·크기·SHA256을 남긴다. 일지·관련 설정·검토한 작은 로그만 04 아래에 명시적으로 stage하고 일반 push한다.

**다음 실행 한 단계:** 별도 승인 후, 기존 lock의 **spconv/cumm wheel 두 개만 PHYSx 아래에 다운로드해 SHA256·METADATA·ELF/PTX를 정적으로 검사한다.** 설치/import/빌드/GPU 실행을 포함하지 않는다. 이는 이미 끝난 dependency 조회 반복이 아니라 아직 보지 못한 실제 wheel 바이너리 내용 확인이다. 그 결과로 sparse trial과 실행기 설계를 확정한다.

해당 단계에서 사용할 download 자식 명령 형식은 다음과 같다. 격리와 실행별 logging 연결 후 사용하며 **이번에는 실행하지 않았다**. `--no-index`여도 lock에 적힌 HTTPS wheel URL에는 다운로드 요청이 발생한다.

```bash
/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python -I -B -S \
  /home/minsujo/Desktop/SH/PHYSx/logs/python-foundation-install-20260921/pip_without_site.py \
  --isolated --cache-dir /home/minsujo/Desktop/SH/PHYSx/cache/pip \
  download --only-binary=:all: --no-index --no-deps --require-hashes \
  --dest "$PHYSX_REVIEWED_SPARSE_WHEEL_DIR" \
  -r /home/minsujo/Desktop/SH/PHYSx/logs/install-plan-20260921/python-sparse-candidate.lock.txt
```

다운로드 후 import 대신 ZIP metadata와 추출한 공유 라이브러리를 `readelf -d` 등으로 읽는다. ELF 정적 검사도 실제 library load/GPU 성공을 증명하지 않으며, 불명확한 버전·PTX 경로는 그대로 미확인으로 남긴다.
