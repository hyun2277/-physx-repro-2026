# 공식 retrieval_texture_example.py 29354 한 표본 실행 검증

- 실행일: 2026-09-26 (Asia/Seoul)
- 원본 commit: `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`
- 목적: merge 산출물 `model.obj`와 ShapeNetCore 원본을 공식 retrieval 코드로 연결하는지 확인
- 실행하지 않음: 다운로드, ZIP 변경/재다운로드, PartNet 사용, GPU·모델 추론, CLIP 다운로드, Blender, GT 생성, 학습, 전체 평가

## staging과 입력

새 staging에 29354만 배치했다.

- staging: `/home/minsujo/Desktop/SH/PHYSx/staging/retrieval-29354-20260925T181057Z/`
- merge 입력 복사본: `phy_dataset/29354/model.obj`
- 단일 항목 `finalindex.json`: `29354 -> shapenet/04379243/db406d9b2a94bce5622d7484764b58f`
- ShapeNet 상대 경로: `shapenet/04379243/db406d9b2a94bce5622d7484764b58f/models/model_normalized.obj`, `.mtl`, `images/texture0.jpg`
- `CUDA_VISIBLE_DEVICES=''`, `PYTHONDONTWRITEBYTECODE=1`

고정 원본 `finalindex.json`의 29354 값과 staging의 단일 항목이 일치하는 것을 실행 전 확인했다. 기존 merge staging과 최소 추출물은 복사만 했고 수정·이동·삭제하지 않았다.

## 실행 결과

- 명령: `envs/physxgen/bin/python .../dataset_toolkits/retrieval_texture_example.py --index 0 --range 1`
- 종료 코드: **1**
- stdout: 비어 있음
- stderr: `trimesh.proximity`의 `source_mesh.nearest.on_surface(...)`에서 `ModuleNotFoundError: No module named 'rtree'`
- top-level `trimesh`/Pillow import는 통과했으나, UV 최근접 표면 계산에 필요한 런타임 의존성이 없었다.
- 동일 명령은 반복하지 않았다. 패키지 설치·다운로드도 하지 않았다.

실패 지점은 공식 코드 52행의 최근접 표면 계산이며, 따라서 `model_tex.obj` export(155행)까지 도달하지 않았다. 생성된 `model_tex.obj`, MTL, texture 참조는 **없음/검사 불가**다. staging에 남은 `exp_texture0.log`는 시작 기록만 담고 있다.

상세 stdout/stderr, 종료 코드, staging inventory는 `/home/minsujo/Desktop/SH/PHYSx/logs/retrieval-29354/20260925T181057Z/`에 보존했다. 입력 및 finalindex hash는 [hash 목록](../자료확보/evidence/2026-09-26-retrieval-29354-hashes.txt)에 기록했다.

## 다음 단계 판정

다음 retrieval 단계로 진행하려면 현재 지정 Python 환경에 `rtree`를 제공해야 한다. 이번 요청 범위에서는 설치하지 않았으므로, **다음 단계 진입은 `rtree` 확보 전까지 막혀 있다.** 이는 재질 품질이나 논문 정량평가 판정이 아니다. 7271은 ShapeNet 매핑이 없어 계속 제외한다.

데이터·mesh·texture·staging 출력·캐시·인증정보는 Git에 추가하지 않았다.
