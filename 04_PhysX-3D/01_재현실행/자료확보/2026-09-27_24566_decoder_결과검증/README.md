# 24566 articulated decoder 결과 검증

## 실행·산출물 무결성

실행 `20260926T221319Z-a9491be93452`는 최종 `status=success`, `child_exit_code=0`이다. 5개 단계의 `exit_code.txt`, 모든 child exit code가 0이고 `SUCCESS.json`에 기록된 모든 output의 경로·크기·SHA256을 다시 계산해 일치함을 확인했다.

- physics child: torch peak allocated 4,658.359 MiB, nvidia-smi 표본 peak 9,062 MiB
- mesh child: torch peak allocated 16,830.444 MiB, nvidia-smi 표본 peak 19,934 MiB
- 28,000 MiB 감시 상한과 4,607 MiB reserve 정책 안에서 종료
- `mesh_physics_raw.pt`: 129,993,591 bytes, SHA256 `25f218fb73d8638b06eed2cbdb9d2b361fa3337834e31ee50361e4746186ebb5`
- `mesh.obj`: 49,815,067 bytes, SHA256 `9e184a51454bd711d75f682bb00cd85c4c5bc00a5bf6fd00d52b955da357f888`

raw 결과는 vertices `(613164, 3)`, faces `(1226344, 3)`, vertex attrs `(613164, 6)`, raw vertex physics `(613164, 32)`이며 모두 유한하다. 공식 property head 결과는 `(613164, 14)`이고 유한하다. OBJ를 CPU로 다시 열었을 때 정점·face 수가 raw tensor와 일치했다.

## GT와 공식 group 판정

GT JSON은 group 0에 parts `0,1,2,3,4,5,7`을 둔 fixed base, group 1에 drawer part `6`을 둔다. group 1의 parent는 `0`, movement type은 `B` translation이다. annotation의 8개 값은 direction `[0,0,1]`, position `[-0.0033322205,0.4470840991,0.0038695019]`, range `[0,0.803352]`이다.

공식 계산 `round(max(group_id))+1`은 group-id 범위 `[-0.0379811, 0.2789923]`에서 predicted group 수를 1로 정했다. 모든 613,164개 정점, 1,226,344개 face, 전체 면적 8.6170759가 group 0이다. group 0은 3개 연결요소이고 크기는 346,700, 258,412, 8,052 정점이다. 예측 group 1은 정점 0, face 0, 면적 0, 연결요소 0이다.

따라서 GT는 articulated 2-group 물체이지만 공식 예측은 fixed 1-group이며, 표본 단위 관절 유무 판정은 **false negative**다. 움직이는 group에 해당하는 실제 표면 영역도 형성되지 않았다.

## 공식 indexing과 수정 후보

예측 group 수가 1이므로 공식 `indexing` 결과는 빈 배열이다. 별도로 저장한 indexing 수정 후보도 `groups=[]`이다. 수정 후보가 관절을 복원한 결과는 없으며, 공식 결과와 섞어 해석하지 않는다.

GT part와 생성 mesh vertex 사이의 공식 직접 대응이 없으므로 parent, direction, position, range의 수치 정확도는 판정하지 않는다. audit의 `gt_annotation.json`에 표시된 object 문자열 `27281`은 구형 audit 코드의 fallback label 오류다. 실제 입력 경로·SHA256과 내부 `group_info`는 24566 JSON이며 이번 통계는 원본 JSON을 직접 다시 읽어 object ID를 24566으로 고정했다.

scale, density, affordance, description, 30-view 평가와 논문 전체 정량평가는 평가하지 않았다. preview는 기존 mesh 정점의 CPU 정사영이며 새 모델 추론이나 Blender 렌더가 아니다.
