# 29354 conditioning render·transforms 정적 preflight

- 기준 기록: `d7d8003`
- 공식 source HEAD: `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`
- 대상: 기존 성공 `model_tex.obj` 29354 한 건
- 수행하지 않음: merge/retrieval 재실행, 다운로드, PartNet/전체 데이터, Blender 설치·렌더, 추론, 학습, 전체 평가

## 공식 코드 점검

`dataset_toolkits/render_cond.py`는 다음 경로와 인자를 요구한다.

- `--output_dir/metadata.csv` 필수
- metadata의 `sha256`, `local_path` 사용; `--instances`로 한 항목 필터 가능
- 기본 `--num_views=24`, `--max_workers=8`
- 각 표본은 `renders_cond/<sha256>/`에 출력되고 Blender `blender_script/render.py`가 `transforms.json`을 기록
- Blender 경로는 `/tmp/blender-3.0.1-linux-x64/blender`
- 없으면 공식 `_install_blender()`가 `sudo apt-get update`, 시스템 라이브러리 설치, Blender 3.0.1 다운로드·압축 해제를 수행

카메라는 `np.random.rand()` offset으로 Hammersley sphere sequence를 시작하고, `np.random.uniform()`으로 1,000,000개 후보에서 radius/FOV를 뽑는다. 코드에 seed 고정이 없고 기본 view 수는 24다. 따라서 논문에서 언급된 고정 30-view 평가 조건과 동일하다고 말할 수 없다.

## 29354 staging

- staging: `/home/minsujo/Desktop/SH/PHYSx/staging/render-cond-29354-20260925T185009Z/`
- 복사한 mesh: `phy_dataset/29354/model_tex.obj`
- 원본 model_tex SHA256: `e58a15b42169119b66da9db751e25ed00c0c57d41de3db83d022538617532633`
- 복사본 SHA256: 동일
- 최소 metadata: `datasets/PhysXNet/metadata.csv`, `sha256=29354_`, `local_path`는 staging mesh 절대경로
- intended command는 preflight에 기록했으나 Blender 부재로 실행하지 않음

Python `pandas`, `numpy`, `easydict` import는 통과했다. 그러나 `/tmp/blender-3.0.1-linux-x64/blender`가 없었다. 공식 코드가 요구하는 apt/sudo와 외부 Blender 다운로드는 이번 범위에서 금지했으므로 즉시 중단했다.

- 로그: `/home/minsujo/Desktop/SH/PHYSx/logs/render-cond-29354/20260925T185009Z/`
- 종료 코드: `2`
- abort reason: `official render_cond requires missing Blender 3.0.1; apt/sudo/download prohibited`
- 생성 conditioning image 수: `0`
- `transforms.json`: 생성되지 않음

이번 결과는 `model_tex.obj`와 최소 metadata 연결 및 공식 camera 생성 규칙의 정적 확인이다. conditioning image·transforms 생성 성공이나 논문 동일 평가 조건을 의미하지 않는다. 다음 조치는 시스템 변경 없이 PHYSx 내부에 승인된 Blender 3.0.1 실행 파일과 필요한 런타임 라이브러리를 준비하는 것이다.

데이터·mesh·이미지·ZIP·모델·캐시·인증정보는 Git에 추가하지 않았다.
