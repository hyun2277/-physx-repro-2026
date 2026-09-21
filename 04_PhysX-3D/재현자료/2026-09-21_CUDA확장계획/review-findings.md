# 조사 범위와 판단 근거

이 문서는 [확장 계획](README.md)의 근거 목록이다. 2026-09-21, 기준 저장소 commit `a244a00`에서 검토했다. 현재 설치 버전은 dist-info를 읽었고 기존 170개와 일치했다. 소스·문서 조회와 정적 판단이며 설치/빌드/연산 검증이 아니다.

## 재조사하지 않은 항목

기존 `source-pins.json`의 PhysX/확장 SHA, 169개 기본 wheel lock, sparse 후보 2개 URL/SHA, CUDA12.8.1/GCC13.3 선택 근거, CLIP 다운로드 패치, 모델 revision을 재사용했다. 최신 버전/HEAD 탐색, 새로운 dependency resolver 미리보기, 기본 PyTorch GPU 재실행은 하지 않았다. **새 pin은 없다.**

추가 조회 이유는 세 가지였다: 실제 import/실행 분기에 따라 필수 여부가 달라지는 문제, SM120에서 아직 확인하지 못한 sparse/JIT 경로, 최소 검사에서 실제 native kernel을 호출할 API 확인이다. 고정 raw source 일부는 웹 캐시 조회에 실패해 같은 SHA의 공식 raw URL로 텍스트를 읽었다. 다른 fork나 최신 HEAD로 대체하지 않았다. 전체 소스 checkout이나 모델 파일은 내려받지 않았다. 추가 원문 조회의 모든 HTTP stdout/exit를 수집한 것은 아니므로 존재하지 않는 실행 로그를 사후 작성하지 않는다.

## 필수/선택 구분: 고정 PhysX 소스

모든 아래 PhysX 링크는 `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`를 가리킨다.

| 확인한 미해결 질문 | 관찰한 코드와 계획 반영 |
| --- | --- |
| 세 renderer를 함께 import하면 세 native rasterizer가 모두 필요한가? | 아니다. [mesh renderer](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/trellis/renderers/mesh_renderer.py#L1)는 nvdiffrast를 최상위 import하지만 [Gaussian render](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/trellis/renderers/gaussian_render.py#L50)와 [OctreeRenderer](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/trellis/renderers/octree_renderer.py#L173)는 native 확장을 선택 경로에서 import한다. |
| Gaussian rasterizer는 공식 example에서도 생략 가능한가? | GLB까지 완료하는 기준이면 필요하다. `example.py → to_glb(gaussian,mesh) → render_multiview(app_rep) → Gaussian render`가 실제 경로다. [postprocessing](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/trellis/utils/postprocessing_utils.py#L399), [example](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/example.py#L254). |
| radiance-field decoder가 있으면 diffoctreerast도 즉시 필요한가? | decode와 render는 다르다. 현재 example의 mesh 영상·Gaussian 기반 GLB 경로에서는 octree render를 호출하지 않는다. 실제 octree 렌더를 선택할 때 필요하다. [renderer 분기](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/trellis/utils/render_utils.py#L42). |
| Kaolin은 아직 설치 대상인가? | 이미0.18.0이 설치됐다. [representations](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/trellis/representations/__init__.py)에서 mesh/FlexiCubes 경로로 연결되고 [vendored FlexiCubes](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/trellis/representations/mesh/flexicubes/flexicubes.py#L9)가 `kaolin.utils.testing`을 import한다. 재설치 대신 검사만 남긴다. |
| vox2seq는 항상 필요한가? | [serialized calc_serialization](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/trellis/modules/sparse/attention/serialized_attn.py#L62) 내부에서 지연 import한다. [mode 연결](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/trellis/models/structured_latent_vae/base.py#L10)은 `full/swin`과 serialized shift 모드를 구분한다. 고정 checkpoint JSON의 실제 attn_mode는 아직 전체 대조하지 않았으므로 조건부로 남긴다. 모델 가중치 다운로드로 확인하지 않는다. |

기본 sparse backend의 [SparseTensor](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/trellis/modules/sparse/basic.py#L38)는 spconv tensor를 만들고, [conv_spconv](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/trellis/modules/sparse/conv/conv_spconv.py#L7)는 sparse convolution을 사용한다. spconv/cumm을 필수 후보로 유지한다. CLIP/utils3d는 보존한 example 원문에서 직접 import가 확인돼 다시 라이브러리 버전을 탐색하지 않았다.

## attention 및 vox2seq 최소 검사 범위

[dense 호출](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/trellis/modules/attention/full_attn.py#L114)은 qkvpacked/kvpacked/일반 세 FlashAttention API를 사용한다. [sparse full](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/trellis/modules/sparse/attention/full_attn.py#L199)은 이에 대응하는 varlen 세 API를 사용한다. [windowed](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/trellis/modules/sparse/attention/windowed_attn.py#L111)와 serialized는 qkvpacked/varlen-qkvpacked를 호출한다. 따라서 일반 dense·varlen 두 함수만 검사해 전체 호출 호환성이 끝났다고 쓰지 않는다.

FlashAttention2.8.3의 `FLASH_ATTENTION_FORCE_BUILD=TRUE`, `FLASH_ATTN_CUDA_ARCHS=120` 근거는 기존 `flash-attention-setup.review.txt`를 재사용했다. CUDA≥12.8에서 `compute_120/sm_120` flag를 추가하는 코드가 존재한다. 정확한 [Python API](https://github.com/Dao-AILab/flash-attention/blob/060c9188beec3a8b62b33a3bfa6d5d2d44975fab/flash_attn/flash_attn_interface.py)와 [C++ 입력 조건](https://github.com/Dao-AILab/flash-attention/blob/060c9188beec3a8b62b33a3bfa6d5d2d44975fab/csrc/flash_attn/flash_api.cpp)을 최소 검사 설계에 사용했다. 빌드 성공은 아직 없다.

vox2seq의 [고정 setup](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/vox2seq/setup.py#L12)은 `CUDAExtension('vox2seq._C')`를 빌드한다. [CUDA wrapper](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/vox2seq/vox2seq/__init__.py#L4)는 `encode(coords,permute,mode)` / `decode(code,permute,mode)`이고 mode는 `z_order`/`hilbert`다. backend/use_cuda/pure 인자는 없다. [별도 PyTorch wrapper](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/vox2seq/vox2seq/pytorch/__init__.py#L15)가 있어도 부모의 native `_C` import가 먼저 필요하므로 설치 전 fallback으로 제안하지 않는다.

## sparse wheel의 남은 핵심: PTX와 실제 NVRTC

기존 lock의 버전/의존성 상한은 재사용했다. 다음은 기존 자료만으로 해결되지 않았던 runtime 경로를 고정 버전 소스에서 확인한 것이다.

- [cumm0.7.11 CompileInfo/헤더 탐색](https://github.com/FindDefinition/cumm/blob/v0.7.11/cumm/common.py): PTX arch보다 새로운 GPU에서 PTX를 사용할 수 있는 분기가 있다. Linux에서 `which nvcc`로 Conda형 Toolkit 배치를 찾고 조건을 충족하지 못하면 시스템 CUDA 경로로 돌아갈 수 있다.
- [spconv2.3.8 convops](https://github.com/traveller59/spconv/blob/v2.3.8/spconv/csrc/sparse/convops.py): PTX로 실행할 수 있으면 NVRTC를 피하는 경로와 내부 autotuning이 있다. “cu126 이름이니 무조건 실패”나 “한 forward는 커널 딱 한 번”으로 해석하지 않는다.
- [cumm NVRTC 옵션](https://github.com/FindDefinition/cumm/blob/v0.7.11/cumm/nvrtc/__init__.py): 실제 장치 arch로 옵션을 만든다. SM120에 대해 NVRTC12.6이 선택되면 문제가 예상되며 [NVRTC12.6 지원 옵션](https://docs.nvidia.com/cuda/archive/12.6.3/nvrtc/index.html#supported-compile-options)에 SM120이 없다.
- [Blackwell 호환 지침](https://docs.nvidia.com/cuda/archive/12.8.1/blackwell-compatibility-guide/index.html): 일반 PTX 상위 호환 경로와 architecture-specific 예외가 있다. 이 문서를 고정 wheel에 필요한 PTX가 실제 포함됐다는 증거로 사용하지 않는다.
- [spconv conv](https://github.com/traveller59/spconv/blob/v2.3.8/spconv/pytorch/conv.py): 1×1 경로가 torch.mm으로 빠질 수 있어 최소 검사는3×3로 설계한다. 가중치 배치와 coordinate 기준을 고정한다.

현재 Toolkit의 `bin/nvcc`, `lib/libcudart.so`, `targets/x86_64-linux/include/cuda.h`는 존재하고 Toolkit NVRTC는12.8.93이다. Python의 `nvidia-cuda-nvrtc-cu12`는12.8.61이다. **둘 중 어떤 파일을 cumm이 실제 로드할지는 확인되지 않았다.** wheel의 자체 `.libs`/RPATH/NEEDED 및 실제 런타임 경로를 각각 확인한다. 위 version-tag 소스 분석은 wheel 자체 바이너리 검사와 구분한다.

[cumm import](https://github.com/FindDefinition/cumm/blob/v0.7.11/cumm/__init__.py)와 [spconv 설정](https://github.com/traveller59/spconv/blob/v2.3.8/spconv/constants.py)의 editable JIT 차단 옵션은 드라이버 PTX JIT/NVRTC 전체 차단 옵션이 아니다. 기본 GPU 실행기에 없는 Toolkit PATH를 추가하는 것과 wheel 내부 라이브러리 선택을 해결하는 것도 서로 다른 문제다.

## nvdiffrast와 octree의 조건 구분

nvdiffrast0.3.3 [setup.py](https://github.com/NVlabs/nvdiffrast/blob/729261dc64c4241ea36efda84fbf532cc8b425b8/setup.py)는 설치 시 CUDA plugin을 완성하는 방식이 아니다. [ops.py](https://github.com/NVlabs/nvdiffrast/blob/729261dc64c4241ea36efda84fbf532cc8b425b8/nvdiffrast/torch/ops.py)는 `TORCH_CUDA_ARCH_LIST`를 비우고 torch extension load를 호출한다. [PyTorch2.7.1 cpp_extension](https://github.com/pytorch/pytorch/blob/v2.7.1/torch/utils/cpp_extension.py)은 arch 지정이 비고 GPU가0개면 빈 목록 접근 오류가 예상되는 경로를 가진다. 실제로 실패를 재현한 것은 아니다. 기존 버전을 유지하고 단일 GPU 첫 JIT를 별도 빌드+검사 단계로 승인받는 설계를 선택한다.

mip의 [고정 Gaussian API](https://github.com/autonomousvision/mip-splatting/blob/dda02ab5ecf45d6edb8c540d9bb65c7e451345a9/submodules/diff-gaussian-rasterization/diff_gaussian_rasterization/__init__.py)는 `kernel_size`와 `subpixel_offset`을 포함한 settings 및 SH/색, scale+rotation/공분산 중 하나를 요구한다. 다른 Gaussian rasterizer의 간단 예제를 그대로 쓰지 않는다.

diffoctreerast 고정 [voxel wrapper](https://github.com/JeffreyXiang/diffoctreerast/blob/b09c20b84ec3aace4729e6e18a613112320eca3a/diffoctreerast/octree_voxel_rasterizer.py)는 `with_distloss`를 읽지만 같은 파일의 기본 Settings에는 해당 필드가 없어 단순 예제 구성에서 오류가 예상된다. **이 문제를 PhysX의 실제 renderer 실패로 확정하지 않는다.** PhysX [octree settings](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/trellis/renderers/octree_renderer.py#L53)는 EasyDict에 `with_distloss`를 직접 넣고, [Strivec](https://github.com/ziangcao0312/PhysX-3D/blob/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/trellis/representations/radiance_field/strivec.py#L25)의 primitive는 trivec다. 선택 검사도 이 실제 경로에 맞춘다.

Kaolin 최소 native 검사의 근거는 설치된 `envs/physxgen/lib/python3.10/site-packages/kaolin/metrics/pointcloud.py`를 읽은 것이다. `sided_distance`가 `_C.metrics.sided_distance_forward_cuda`를 호출함을 확인했다. import나 GPU 호출은 하지 않았다. 이 검사를 통과하더라도 PhysX가 vendoring한 FlexiCubes의 실제 mesh 산출까지 검증한 것은 아니다.
