# 29354 raw vertex physics 채널 및 CPU 후처리 검증

## 범위와 판정 등급

고정 source HEAD `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`, cached decoder raw tensor, 공식 `property_output_step0100000.pt`만 읽었다. GPU, sampling, physics decoder와 mesh decoder는 실행하지 않았다. 이 문서의 결론은 다음 네 등급을 사용한다.

- **논문에 명시됨**: 논문 v4 및 공식 README가 속성·단위·평가 항목을 직접 서술한다.
- **공식 코드와 checkpoint에서 확인됨**: 고정 source의 데이터 흐름과 실제 weight shape가 일치한다.
- **우리가 제안하는 해석**: 코드 불일치를 해소하는 후보이며 공식 결과로 취급하지 않는다.
- **아직 미확정**: 공개 코드만으로 단위·평가 계약 또는 의도를 확정할 수 없다.

## 32채널이 만들어지는 경로

**공식 코드와 checkpoint에서 확인됨.** `merge_property.py`는 부품별 CLIP embedding 4×768과 14개 물리값을 만든다. 14개 순서는 scale, priority rank, density, group id, parent id, 8개 movement parameter, movement type이다(`dataset_toolkits/merge_property.py` 96–125, 138–156, 180–184행). dataset loader는 이를 각각 3072채널 `property1`과 14채널 `property2`로 읽는다(`trellis/datasets/structured_latent2render_mesh.py` 182–194행). encoder config도 입력 3072/14와 latent 8을 명시한다(`configs/vae/slat_vae_enc_dec_mesh_phy.json` 3–17행).

Property encoder는 두 입력을 각 절반 model width로 투영해 결합하고 8차원 확률 latent를 만든다(`propertyencoder.py` 55–73행, `base.py` 178–235행). Property decoder는 8차원 sparse latent를 두 번 upsample하여 마지막 256채널 feature를 낸다(`decoder_mesh.py` 371–453행). mesh extractor가 이를 cube corner 8개로 reshape하므로 corner당 32채널이고, FlexiCubes interpolation 뒤 최종 `mesh.phy_property`가 vertex당 32채널이 된다(`cube2mesh.py` 109–139행).

학습 renderer는 이 32채널을 **앞 16 language latent / 뒤 16 physics latent**로 분리한다(`mesh_renderer.py` 118–126행). `PropertyOutput`은 두 16채널 입력에 별도 3×3 Conv2d를 적용한다(`decoder_mesh.py` 308–368행). 실제 checkpoint shape도 language `[3072,16,3,3]`, physics `[14,16,3,3]`이다. 따라서 개별 raw 채널 0–15나 16–31에 scale/density 같은 직접 의미가 하나씩 붙는 구조가 아니다. 각 절반은 learned latent이고, 최종 의미는 output head의 혼합 결과에 있다.

학습 loss는 language head를 4×768 CLIP target에, physics head를 14개 GT에 L1로 맞춘다. scale, rank, density, parent id, movement type에는 코드상 정규화가 적용된다(`structured_latent_vae_mesh.py` 184–218, 276–293행).

## 공식 example slice 대조

`example.py` 179행은 language 인자로 `phy_property[:,16:]`, physics 인자로 `phy_property[:,-16:]`를 준다. 32채널 입력에서는 둘 다 정확히 channels 16:32이며 CPU에서 `torch.equal`도 참이었다.

이 동작은 다음 근거들과 일치하지 않는다.

1. 학습 renderer는 language에 `:16`, physics에 `-16:`을 사용한다(`mesh_renderer.py` 120, 125행).
2. checkpoint의 두 head는 각각 독립적인 16채널 입력을 기대한다.
3. 학습 target은 앞 경로를 3072차원 CLIP embedding, 뒤 경로를 14개 physics 값으로 감독한다(`structured_latent_vae_mesh.py` 202–218행).
4. 저장소의 기존 검토 patch도 language slice만 `:16`으로 바꾸고 이를 학습 renderer와의 일치 근거로 기록했다.

따라서 **공식 코드와 checkpoint에서 확인된 사실**은 “공식 example이 두 head에 같은 마지막 16채널을 준다”는 것이다. **우리가 제안하는 해석**은 language만 앞 16채널로 바꾸는 것이 학습 경로와 맞는다는 것이다. 저자의 명시적 정정이나 공식 commit은 확인하지 못했으므로 upstream 의도 확정은 **아직 미확정**이다. CPU 결과에서도 공식 경로와 후보 경로의 language head 통계를 별도로 저장했으며 후보를 공식 출력이라고 부르지 않는다.

## 최종 속성 대응

전체 대응표와 29354 범위는 [`channel_mapping.csv`](channel_mapping.csv)에 있다.

| 속성 | 공식 head 출력 | 공식 후처리 | shape | 단위·의존성 |
|---|---:|---|---|---|
| scale | physics 0 | `x*48+95`, example은 vertex 평균 출력 | `[N]` | cm; 질문 비의존 |
| affordance | physics 1 | 학습 target `1-rank/10`; example은 물체 내 min-max | `[N]` | 무차원; 질문 비의존 |
| material/density | physics 2 | `x*2.8+2.3`, 표시할 때 물체 내 min-max | `[N]` | g/cm³; 질문 비의존. `material.mp4` 이름과 달리 수치 target은 density |
| description | language 3072 | `[N,4,768]` 중 question type 선택 → CLIP text cosine → min-max | `[N]` | 무차원; 질문 문자열·type·CLIP 의존 |
| kinematic group/parent | physics 3/4 | group 최대값·integer 주변 threshold; parent는 `x*.732-.812` | `[N]`씩 | integer-like code; 질문 비의존 |
| kinematic parameter/type | physics 5:13 / 13 | group 평균; type은 `x*4` 후 round | `[N,8]`, `[N]` → 그룹별 `[8]`, scalar 의도 | direction은 무차원. position/range 단위와 type별 range 의미는 미확정 |

**논문에 명시됨.** 공식 README 114–130행은 absolute scale에 Euclidean distance, density·affordance·description map에 PSNR, kinematics에 instantiation distance를 사용한다고 적는다. 논문 v4는 dimension cm와 density g/cm³를 명시한다. 그러나 공개 source에는 이 metric을 실제 집계하는 완성 calculator가 없고 `example_render_gt_foreval.py`는 GT scale 및 map을 저장하는 단계다(141–181행). PSNR data range, 공통 정규화, mask·view 집계 계약은 **아직 미확정**이다.

Fixed object 분기는 `num_group=round(max(physics[:,3]))+1`이 1일 때다(`example.py` 194–203행). 이 경우 kinematic parameter가 추가되지 않고 관절 파일도 생성되지 않는다(263–280행). 이번 29354 예측은 group-id 최대 0.516207이라 `num_group=2`다. 반면 확보된 29354 GT JSON은 group 0만 가진다. 이는 예측과 GT가 다르다는 관찰이며 관절 정확도 판정은 아니다. 또한 공식 211–212행의 group-mask 행/열 indexing은 기존 검토 patch가 수정 대상으로 분리한 부분이므로 이번 CPU 결과에서 관절 parameter/type을 확정 출력으로 만들지 않았다.

## CPU 결과와 preview

공식 physics 경로로 `[381856,14]`를 만들었고 전부 유한했다. scale 범위는 89.853195–111.811874 cm, 평균 99.788567 cm다. density는 0.681129–6.491174 g/cm³다. affordance 표시값은 공식 example 방식의 물체 내 min-max로 0–1이다. description은 slice 불일치와 질문/CLIP 의존성이 있으므로 score preview를 만들지 않았다. kinematics는 위 indexing 문제와 GT 불일치 때문에 시각화하지 않았다.

[`vertex_physics_preview.png`](vertex_physics_preview.png)는 확인된 physics head의 affordance 표시값과 density를 기존 mesh vertex에 연결한 x–z 투영, scale histogram이다. 카메라 렌더, 표면 품질, 물리 정확도 또는 논문 평가 결과가 아니다. 수치·hash·두 language 경로 통계는 [`postprocess_stats.json`](postprocess_stats.json)에 있다.

실행 스크립트는 CPU float32로 1×1 spatial input에 대한 3×3 Conv2d의 중앙 kernel을 적용한다. 이는 padding 1에서 주변이 모두 padding인 공식 head 연산과 같은 대수식이지만, GPU fp16 결과와 비트 단위 동일하다고 주장하지 않는다.
