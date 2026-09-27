# PhysX-3D 공식 코드 패치 모음 (2026-09-21)

## 최신 상태 — Codex 재생성 및 적용 검사 완료

아래 최초 작성 설명보다 이 절을 우선한다. 손으로 작성된 기존 diff를 기준 커밋의 실제
수정 복사본에서 Git diff로 재생성했다. D 드라이브 원본 저장소와 GitHub는 변경하지 않았다.

- 패치 3개 각각 `git apply --check` 및 임시 복사본 실제 적용 성공.
- 3개 패치의 모든 순열(6가지)에서 순차 적용 성공, 적용 내용 일치 및 Python AST 문법 검사 통과.
- 증거·해시: [verification_result.json](verification_result.json).
- 재생성 도구: [regenerate_and_verify.py](regenerate_and_verify.py). D 드라이브 임시 Git 저장소 사용.
- 02와 03의 원래 수정 위치는 겹쳤다. 아래 '범위가 겹치지 않음'이라는 옛 설명은 정정한다.
  새 패치는 적용 문맥을 조정했고 순서별 검사를 실제 수행했다.
- 01은 그룹 bool 선택만 수정한다. 부모 그룹 207행과 빈 그룹 mean/NaN 처리는 미해결이다.
- 02는 대상 description을 한 번 선택·저장한다. seed 및 GT-예측 질문 정렬은 추가 검증 필요.
- 03은 실제 데이터의 숫자순 메시/part 대응을 확인해야 하는 **잠정 패치**다.
- '수정 완료'는 패치 작성·적용 가능성에 한정한다. 모델 정확성·GT 품질·실기 성공을 뜻하지 않는다.
- 현재 00~05 실행 스크립트는 패치를 자동 적용하지 않는다. 원본·패치 실행을 구분해 기록해야 한다.
- 설치·환경·캐시·로그 관련 나머지 지적은 이번 패치 재생성에서 수정하지 않았다.

## 최초 작성 기록

**원칙**: 이 폴더의 `.patch` 파일들은 `D:\physX_dev\repos\PhysX-3D`(pinned commit
`4f54e750a309fe9cd9f20816916ecc0e8a9ae594`)를 **아직 수정하지 않은 상태**에서, 검토·근거 기록용으로
작성한 diff다. **실제로 clone/install/실행한 적 없다.** 5090/Linux 머신에서 저장소를 새로 clone한
뒤, 각자의 신뢰도 등급에 맞게 적용 여부를 판단할 것.

## 패치 목록과 신뢰도 등급

| 파일 | 대상 | 등급 | 한 줄 요약 |
|---|---|---|---|
| `01_example_py_kinematic_map_fix.patch` | `example.py` 211~212행 | **수정 완료**(기계적 근거) | 행/열 인덱싱 버그 — CPU로 독립 재현까지 완료 |
| `02_example_render_gt_foreval_py_des_index_fix.patch` | `example_render_gt_foreval.py` 149~169행 | **수정 완료**(기계적 근거) | `des_index.npy` 무조건 덮어쓰기 버그 — 루프 밖으로 호이스트 |
| `03_example_render_gt_foreval_py_meshname_fix_설계근거.patch` | `example_render_gt_foreval.py` 149~154행 | **★실기 검증 필요★**(설계 근거만 있음) | `meshname` 재사용 버그 — 저장소 내 유사 코드(`dataset_toolkits/merge_property.py`) 패턴을 따랐으나 실제 데이터로 확인 못함 |

"수정 완료" 등급 = 파일 자체의 텐서 shape·제어 흐름만으로 버그와 올바른 수정 방향을 실행 없이도
확정할 수 있었던 것. "실기 검증 필요" 등급 = 저장소 다른 곳의 유사 패턴을 근거로 설계는 했지만,
실제 PhysXNet 샘플 데이터로 돌려보기 전까지는 옳다고 확정할 수 없는 것.

## 이 패치들이 다루지 않는 것 (의도적으로 범위 밖)

- **`example.py` 207행**(부모 그룹 임계값 계산 `phy[...,4][kinematic_map[:,(group_ind-1)*2]]`):
  0/1 long 텐서를 인덱스로 쓰는 별도의 팬시 인덱싱 버그다. 01번 패치가 211~212행을 고쳐도 이
  버그는 그대로 남는다. Codex 대조메모 1번이 지적한 대로 "그룹의 부모 ID를 어떻게
  집계·반올림·검증할지는 별도 설계와 데이터 검증이 필요"해서, 추측성 패치를 만들지 않고
  **미해결로 명시**한다. `PhysX-3D_수정완료_vs_실기검증필요.md`의 실기 검증 목록 참고.
- **정량 채점 코드 자체**(Euclidean/PSNR/Instantiation distance 계산·집계): 저장소에 이 로직이
  아예 없다(단, `trellis/utils/loss_utils.py:34`에 `psnr` 함수는 존재 — Claude_독립검증.md
  정정본 §4 참고). 새로 구현해야 하는 영역이라 "패치"가 아니라 별도 신규 구현 대상이다.

## 적용 방법 (아직 실행 안 함, 참고용)

```bash
cd PhysX-3D   # 5090 머신에서 새로 clone한 폴더, pinned commit 확인 후
git apply --check ../PhysX-3D_공식코드_패치/01_example_py_kinematic_map_fix.patch
git apply ../PhysX-3D_공식코드_패치/01_example_py_kinematic_map_fix.patch
git apply --check ../PhysX-3D_공식코드_패치/02_example_render_gt_foreval_py_des_index_fix.patch
git apply ../PhysX-3D_공식코드_패치/02_example_render_gt_foreval_py_des_index_fix.patch
# 03번은 실기 검증 전까지 "잠정 패치"이므로, 적용 여부는 실제 PhysXNet 데이터를 받은 뒤
# 파트 개수/objs 폴더 파일 개수 대응을 직접 확인하고 판단할 것(assert가 걸리면 그 자체가
# "이 물체는 이 패턴이 안 맞는다"는 신호이니 무시하지 말고 원인을 먼저 조사).
git apply --check ../PhysX-3D_공식코드_패치/03_example_render_gt_foreval_py_meshname_fix_설계근거.patch
```

01번과 02번은 서로 다른 파일(01) 또는 겹치지 않는 줄 범위(02, 03은 같은 파일이지만 02는
149~154행 근처는 손대지 않고 158행 이후만, 03은 149~154행만 건드리므로 순서 무관하게 독립
적용 가능 — 단, 둘 다 적용할 때는 03을 먼저 적용해 149행 부근을 먼저 바꾼 뒤 02를 적용하는
편이 diff 충돌 가능성이 가장 낮다).

## 근거 문서
- `../PhysX-3D_Claude_독립검증.md` §7, §8 — 각 버그의 상세 코드 대조·실행 재현 기록
- `../PhysX-3D_Claude검증_대조메모.md` — Codex의 교차검증(이 패치들을 만들게 된 직접 계기)
- `../PhysX-3D_수정완료_vs_실기검증필요.md` — 이 패치들을 포함한 전체 항목의 최종 분류
