# RTX 5090 adapter fidelity suite

## 판정

**`partially_verified`**. channel tiling, output-channel tiling, memory-bounded
GroupNorm, 그리고 decoder child-process 분리는 아래의 실제 GPU 비교 범위에서
수치적으로 동등했다. 그러나 int32 한계를 넘는 원래 production layer는 원본 spconv
경로 자체가 실행할 수 없으므로 직접 비교할 수 없고, output-channel tiling은
artifact-complete 25표본의 성공 로그에서 대형 production fallback으로 관측되지
않았다. 따라서 이 결과는 전체 원본 환경 또는 논문 Table 2의 동등성 주장이 아니다.

실행은 saved 29354 latent와 고정 decoder checkpoint만 사용했다. image sampling,
conditioning render, download, 학습, 기존 artifact 변경은 수행하지 않았다.

## 비교 조건과 허용오차

GPU 1 (`GPU-843dced4-ee97-dbb8-36c9-343fe13b7647`)만 사용했고, 실행 전 compute
process 부재를 확인했다. CUDA 12.8.1 overlay, GCC/G++ 12, Native spconv을
사용했다. hard limit은 28,000 MiB, reserve는 4,607 MiB로 고정했다.

각 원본 연산은 같은 입력으로 두 번 실행했다. adapter 허용 범위는 사후 고정값이
아니라 다음으로 정했다.

`max(원본 반복 max-abs 오차 × 4, dtype epsilon × reference max-abs × 16)`

relative L2와 cosine도 같은 원본 반복 오차와 dtype epsilon을 바탕으로 정했다.
모든 수치는 [fidelity_summary.json](fidelity_summary.json)에 있다.

## adapter별 결과

| 대상 | 실제 비교 shape / dtype | 원본 반복 | adapter 대 원본 | 결과 |
|---|---|---|---|---|
| channel-tiled Native SubMConv3d | `135,544 × 512 → 256`, fp16; property decoder checkpoint `upsample.1.out_layers.0.conv`의 KRSC `[256,3,3,3,512]` weight | max abs `0`, relative L2 `0` | max abs `3.0`, mean abs `0.0324055`, relative L2 `8.0076e-4`, cosine `0.99999982` | pass |
| output-channel-tiled Native SubMConv3d | 같은 actual checkpoint weight·coordinate structure; input 256, output 96 forced tile | max abs `0`, relative L2 `0` | max abs `3.0`, mean abs `0.0324055`, relative L2 `8.0076e-4`, cosine `0.99999982` | pass |
| memory-bounded GroupNorm | `131,072 × 256`, groups 32, batch `[50,000,81,072]`, checkpoint `upsample.1.out_layers.1`, fp16/fp32, affine on/off | 네 case 모두 max abs `0`, relative L2 `0` | fp16 max abs `9.7656e-4`/`1.9531e-3`; fp32 `4.7684e-7`/`9.5367e-7`; 모두 finite·허용범위 통과 | pass |
| decoder child-process 분리 | 같은 29354 cached latent·두 decoder checkpoint·현재 adapter | 해당 없음: single control과 split child는 다른 process scheduling | vertices max abs `1.1921e-7`, attrs `2.9802e-7`, physics `5.9605e-7`; faces exact | pass |

conv probe는 saved 29354 `phy_coords` 33,886행을 공간적으로 분리한 네 복사본으로
135,544행을 만들었다. local coordinate pattern, actual batch, production fp16,
checkpoint kernel/channel layout을 보존했지만 production의 2,168,704행 전체는
원본 path가 int32 한계를 넘으므로 비교 대상이 아니다.

GroupNorm은 실제 checkpoint의 affine weight/bias, groups=32, eps=`1e-5`를 썼다.
두 batch의 point 수를 의도적으로 비균일하게 유지했다. streaming 구현은 각 batch와
group의 모든 point·channel에 대해 biased variance를 계산하므로 spatial chunk마다
독립 정규화하지 않는다. inference-only이며 backward는 검증 범위 밖이다.

## child-process control

과거 29354 sequential artifact는 현재 adapter와 정점 수가 `381,856` 대 `381,858`로
달라 direct reference로 부적절했다. 이 차이를 child-process 효과로 해석하지 않고,
현재 adapter를 사용한 새로운 single-process control과 physics-child → serialized
intermediate → mesh-child 결과를 비교했다. 두 결과는 vertices `[381,858,3]`,
faces `[763,680,3]`, attrs `[381,858,6]`, vertex physics `[381,858,32]`에서 유한했고,
faces는 exact였다.

single control의 관측 nvidia-smi peak는 21,090 MiB, split physics/mesh child의
peak는 각각 17,706/20,034 MiB였다. 모두 28,000 MiB 제한 아래였다.

## production coverage와 미검증 경로

* channel tiling은 29354 original adapter log 및 이번 control의 실제
  `N=2,168,704, C=512, O=256, tile=256` 호출에서 확인됐다.
* memory-bounded GroupNorm은 24566·29806의 decoder logs와 이번 control에서
  확인됐다. 이번 control의 최대 확인 rows는 `2,168,704 × 256` fp16이다.
* output-channel tiling은 작은 actual-checkpoint forced test에서만 원본과
  비교했다. 성공한 25표본의 대형 trace에서 이 fallback의 필요/실행은 확인되지
  않았다. 27281의 output-byte 초과 경로는 이후 OOM으로 실패해 artifact-complete
  표본이 아니다.
* 모든 25표본의 각 layer·fallback branch를 complete trace로 재감사하지 않았다.
  따라서 threshold 아래 원본 forward가 적용된 경로와 trace가 없는 fallback은
  `unverified coverage`로 남긴다.
* sparse coordinate order, finite output, bias, Native algo는 tested cases에서
  보존했다. fused add, training/backward, groups != 1 convolution, fused activation,
  다른 spconv algorithm은 adapter가 fail-closed로 거부하며 검증하지 않았다.

## 범위 밖 주장

이 suite는 RTX 5090 adapter가 tested numerical cases에서 계산 의미를 보존하는지
확인한 것이다. 원본 CUDA 11.8 전체 환경, complete original end-to-end process,
논문 Table 2, physics/kinematics accuracy, 또는 artifact 품질의 동등성은 검증하지
않는다.

## 참조

* source HEAD: `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`
* fidelity run: `/home/minsujo/Desktop/SH/PHYSx/logs/rtx5090-adapter-fidelity/20260927T145928Z-e23ec5022a2b`
* run result SHA256: `de3af97dd4877224dd6cee89125a4c3552f0a56f1bdeb1ccffa09ed34e90b202`
* operation metrics SHA256: `06e7f14f818d6c0cb67e584c58d4a93d4a0fc2051b2f967626ea5e9aedcba1ad`
* child comparison SHA256: `29d194d81c8d8d1eeffbabd054493b6ebb73754089f0663ad3bd142af17ae97e`
