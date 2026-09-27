# 29806 C형 회전 관절 decoder 결과 검증

29806 decoder run `20260927T050730Z-8271ccb5f82b`의 5개 단계는 모두 exit code 0, child exit code 0, `SUCCESS.json` output hash 재계산 일치로 확인됐다. raw mesh/physics와 OBJ는 CPU에서 다시 열어 검증했다.

- mesh: vertices `(180260, 3)`, faces `(360512, 3)`, raw physics `(180260, 32)`, vertex attrs `(180260, 6)`; 모두 유한
- property head: `(180260, 14)`, 유한
- physics child peak: torch 2,234.963 MiB, nvidia-smi 표본 4,298 MiB
- mesh child peak: torch 12,587.484 MiB, nvidia-smi 표본 3,526 MiB

GT는 fixed group 0과 parent 0인 C형 회전 door groups 1·2·3의 총 4 groups다. 공식 식 `round(max(group_id))+1`은 predicted group 수 2를 산출했다. group 0은 157,271 vertices, 314,678 majority faces, 면적 2.2148623이다. group 1은 22,989 vertices(12.75%), 45,834 majority faces, 면적 0.3133133(12.39%)이므로 실제로 비어 있지 않은 예측 표면 영역이다.

그러나 predicted group 1은 121개 연결요소로 분절되어 있고 가장 큰 요소도 그 group 정점의 34.4%다. GT의 세 회전문과 group 수가 일치하지 않으며, GT part와 생성 mesh vertex의 직접 대응도 없다. 따라서 이는 **articulation surface present but group-count underprediction**으로 기록하며, parent·direction·position·range 정확도나 특정 door 대응을 주장하지 않는다.

official indexing은 parent expression shape mismatch를 기록하고 `official_row_index_result_shape=[2,8]`만 생성했다. 별도 indexing correction candidate는 group 1의 22,989개 정점을 선택한 결과지만 공식 결과가 아니며, 관절 대응 정확도의 근거로 사용하지 않는다.

24566은 GT 2-group drawer에 대해 predicted group 수 1, moving surface 0으로 false negative였다. 29806은 nonzero moving surface를 냈지만 GT 4-group보다 적은 2 groups다. 두 표본은 단일 conditioning-image-to-decoder 실행 결과일 뿐이며 일반 성능이나 논문 정량평가를 뜻하지 않는다.
