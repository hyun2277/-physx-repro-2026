# PhysX 정량 평가 기반 코드와 CPU 검산

이 코드는 [2026-09-21 평가 규약 초안](../평가규약/2026-09-21_초안/평가규약.md)의 확정된 목록 보존·기록 조건과 수학 연산을 구현한다. **실제 데이터 평가기 완성본이 아니다.** 현재 실행기는 작은 합성 자료만 계산하며 공식 test 추론/전체 평가·GPU·렌더링·다운로드·설치 경로는 없다. 모든 결과는 `paper_equivalent=false`, `claim=proposal_cpu_check`로 기록한다.

## 구현 범위

| 파일 | 구현·차단 범위 |
|---|---|
| `physx_eval/manifest.py` | 기존 원본 NPY의 고정 SHA256을 검사하고 CSV와 모든 test 행을 대조. 1,000행/972개 ID의 순서·중복·원본 index·등장 번호 유지. `item_key=test-000000` 형태로 중복 출력 충돌 방지. 집계 가중치는 결정하지 않음 |
| `physx_eval/mapping.py` | 파일 존재·SHA256·프로젝트 경계, object/source row/input hash, 조건 뷰와 평가 뷰, camera/context, 단위, 숫자 배열 shape, 질문/part label·JSON index·mesh 파일명/hash 연결 검증. 잘못되거나 미확정이면 중단 |
| `physx_eval/runner.py` | 항목×지표의 성공/차단/실패, 이후 미실행을 구분. 잠금으로 같은 세션 중복 실행 방지. manifest/config/code/Python 버전 및 파일 대응이 같은 성공만 재사용. 실패·중단·손상은 명시적 재시도 필요 |
| `physx_eval/metrics.py` | PSNR 4종의 단일 뷰 수학 연산, scale L2, 명시적으로 선택한 CD 정의와 방향별 F-score. 30뷰 외관 PSNR의 산술 평균 helper. COV/MMD와 관절 ID는 미구현 오류로 중단 |
| `configs/unresolved.json` | 미확정 항목은 null. threshold 0.05만 알더라도 거리 해석·좌표·정규화·경계 판정 없이는 FS 계산 불가. 이 파일로 실제 점수가 나오지 않아야 정상 |
| `configs/synthetic-scale.json`, `tests/` | 합성 검산에만 사용하는 제안 설정과 작은 수작업 정답. 실제 PhysX 입력/GT/카메라 조건으로 전용 금지 |
| `run_cpu_checks.py` | 기존 `workspace_runner.py`의 bwrap·허용 환경변수·실행별 로그 방식에서 CPU 전용으로 분리. 읽기 전용 시스템/환경, GPU 장치 숨김, 네트워크 격리, 고유 로그 폴더만 쓰기 허용. 보호 완화 fallback 없음 |

외관의 30뷰 평균 helper는 전달된 **서로 다른 30개 뷰 점수의 산술 평균만** 검산한다. 카메라가 논문 조건대로 무작위 단위구에서 생성됐는지 증명하거나 카메라를 선택·렌더하지 않는다. 항목 runner는 현재 단일 prepared view만 지원한다. CD의 거리/제곱거리·양방향 합/평균 및 FS의 경계/0 처리 선택도 수학 연산 구현이며 논문의 정확한 구현 확인을 대신하지 않는다.

## CPU 검산 실행

기존 Python 환경의 표준 라이브러리만 사용한다. 추가 설치는 필요 없다. 아래 한 명령은 **합성 CPU 검산과 기존 split 메타데이터 읽기만** 수행한다.

```bash
/usr/bin/python3 -I -B -S /home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/evaluation/run_cpu_checks.py
```

자식 검산은 `/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python -I -B -S -u`로 실행한다. 원래 HOME 값은 유지하되 읽기 전용이며, TMP/XDG 경로는 실행 폴더 아래로 지정한다. 실행기는 Git을 호출하지 않는다. 격리 진입 실패도 로그로 남기고 종료하며, 자동으로 호스트에서 검산을 다시 실행하지 않는다.

실행마다 `/home/minsujo/Desktop/SH/PHYSx/logs/evaluation-cpu-20260921/<UTC시각-UUID>/`에 다음을 새로 작성한다. 기존 폴더/로그를 덮어쓰지 않는다.

- `command.json`, `code-hashes.json`, `versions.json`: 실제 argv·시각·소스 hash·Python 버전·GPU 장치 부재/네트워크 interface 확인.
- `stdout.log`, `stderr.log`, `result.json`: 파일에 계속 기록되는 출력과 종료 코드. 의도한 차단 사례의 traceback은 해당 합성 세션 안에 따로 보존.
- `checks.json`: 각 테스트 상태와 시간, 전체 실패/오류 수. 테스트 통과는 실제 GT나 논문 점수를 검증했다는 뜻이 아님.
- `official-test-manifest.json`, `manifest-summary.json`: 원본 순서의 목록과 아직 빈 binding 상태. 실제 입력/GT 파일 확보를 뜻하지 않음.
- `temporary/fixtures/`: 작은 합성 파일·세션·재시도 기록. 기존 데이터/모델과 분리하고 Git에 통째로 넣지 않음.

## Manifest와 대응 파일의 계약

`cli.py`는 `manifest`, `validate`, `synthetic-run`만 제공한다. `--root`는 필수이고 모든 파일 경로는 해당 root 안에 있어야 한다. 출력 파일은 새 파일로만 생성한다. 직접 CLI를 실행할 경우에도 위와 같은 CPU 격리·로그 래퍼를 사용해야 한다. 이 버전은 일반 실제 데이터 평가 명령을 제공하지 않는다.

```text
cli.py --root <PHYSx> manifest --csv <기존 대응 CSV> --npy <기존 원본 NPY> --output <새 manifest.json>
cli.py --root <PHYSx> validate --manifest <manifest.json> --config <config.json> --output <새 validation.json>
cli.py --root <PHYSx> synthetic-run --manifest <합성 manifest.json> --config <합성 config.json> --session <새 세션 폴더>
```

`manifest`는 NPY 뒤 1,000행과 CSV의 ID/index/occurrence를 전부 비교한다. 생성되는 각 항목은 `item_key`, `test_index`, `source_index`, 문자열 `object_id`, `occurrence`, 빈 `bindings`를 가진다. 중복 정책은 null로 남으며, 공식 test manifest는 `synthetic-run`에서 거부한다. `validate`는 파일/metadata 대응 검사이며 숫자 지표 계산을 하지 않는다.

한 항목의 `bindings[metric]`에는 `input`, `prediction`, `ground_truth` 파일 reference가 필요하다. 각 reference는 root 안의 경로와 실제 SHA256을 가진다. input reference에는 `object_id`와 **조건 영상** `view_id`가 추가된다. prediction/GT 파일은 별도의 JSON envelope다.

```text
schema_version = 1
role = prediction 또는 ground_truth
item_key / object_id / source_index = manifest 항목과 정확히 일치
input_sha256 / input_view_id = 같은 조건 입력 reference와 일치
context = 해당 지표 설정의 context와 일치
payload = {values: [...], unit: 명시 단위, view_id: 평가 뷰 ID}  # PSNR
          {values: [...], unit: 명시 단위}                      # scale
          {points: [[x,y,z],...], unit: 명시 단위}              # CD/FS
```

현재 어댑터 계약은 위 prepared JSON을 대상으로 한다. 원래 PhysX raw head/mesh/JSON에서 이 파일을 생성하는 실제 데이터 변환기는 아직 없다. 입력 파일의 hash가 맞는지 검사하지만 입력 이미지를 디코딩하지 않으며, mesh의 형태/texture/관절 의미까지 검증하지 않는다.

모든 지표는 `authority`, `unit`, `normalization`, `alignment=already_aligned`, `context`가 필수다. `normalization`은 명시한 identity 또는 양쪽에 공통 적용하는 fixed_affine만 지원한다. 개별 min-max·자동 단위 변환·ICP·scale fitting은 구현하지 않았다. 상수 맵을 조용히 0맵으로 바꾸지 않는다.

PSNR context는 `coordinate_frame`, `normalization_id`, `camera_set_id`, `camera_sampling`, `camera_parameters`, `view_ids`, `image_shape`, `color_space`, `background`, `mask_policy`를 요구한다. 행렬 shape/유한성, near/far를 검사한다. `image_shape`는 HW 또는 HWC, `resolution`은 **[width,height]**다. pred/GT 실제 배열 shape와도 대조한다. camera_parameters는 extrinsic 4×4, intrinsic 3×3, resolution, near, far, convention을 모두 제공해야 한다. 누락된 camera seed/분포 등의 실제 규약은 기존 초안의 미확정 사항이며 이 검증기로 원문 일치가 확정되지 않는다.

density/affordance/description은 `part_correspondence=explicit_file_map`, `parts` 대응 목록, `annotation` reference도 요구한다. 목록의 label·parts_index·mesh_filename·mesh reference를 JSON `parts[].label`과 대조한다. 설명 맵은 question_type/text/target_part, gt_map_definition, text_encoder_revision도 필요하다. annotation envelope의 object_id와 parts를 제공하는 단계 역시 실제 PhysX 파일 어댑터에서 검증해야 한다. 파일명 숫자=배열 위치를 자동 가정하지 않는다.

## 실패·재개·집계 경계

세션마다 manifest/config/code hash와 Python 버전을 고정하고 입력 snapshot을 저장한다. 재개 시 snapshot·완료 checksum·항목/지표 identity를 다시 확인하며, 이전 성공이라도 참조 파일의 현재 hash와 대응을 재검증한다. 성공 기록이 다른 항목과 혼입되거나 파일이 손상되면 재사용하지 않는다. 설정이나 코드가 바뀌면 **새 세션**을 사용한다.

항목별 `attempt-<순번>-<UTC시각-UUID>/`에 command/시작·끝 시각/stdout/stderr/exit/result/checksum을 남긴다. 첫 실패 후 나머지는 `not_attempted`, 기존 실패·중단 기록은 `retry_required`다. 동일 계약의 실패를 재시도하려면 API의 `retry_failed=True` 또는 CLI의 `--retry-failed`를 명시해야 한다. 재시도는 새 폴더에 쓰며 기존 실패 기록을 보존한다. 완료되지 않은 기록을 성공으로 추정하지 않는다.

`aggregation.mode=disabled` 및 null인 duplicate/failure policy·denominator가 현재 버전의 명시적 상태다. 세션 결과는 성공/재사용/실패/차단/미실행 건수만 보고하고, `aggregation.status=blocked`, `final_score=null`을 유지한다. 1,000이나 972, 또는 성공한 항목 수를 최종 분모로 조용히 선택하지 않는다. COV/MMD·관절 ID와 N/A 정책도 구현되지 않았다.

실제 데이터 없이는 입력/GT의 의미적 일치, mesh·texture 좌표/단위, 관절 변환, 질문 GT map의 정답성, 논문 카메라 조건을 확인할 수 없다. 해당 규약 확인과 데이터 어댑터·렌더러·관절 ID 연결 후에만 다음 구현 단계로 진행할 수 있다.
