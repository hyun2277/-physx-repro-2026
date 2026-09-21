# 공식 table 예제 완료 기록

사용자가 터미널에서 실행한 `20260921T122021Z-415cd02be5`는 2026-09-21 21:22 KST에 종료0으로 완료했다. 설치·기본 연산·모델 실행·출력 검증을 구분한 설명은 [실험일지](../../../실험일지/2026-09-21_공식예제_03_실행결과.md)에 있다. 이번 게시를 위해 추론·설치·GPU 실험을 재실행하지 않았다.

## 먼저 읽을 기록

- [터미널 전체 결과](evidence/logs/official-example-20260921/terminal-runs/20260921T122021Z-415cd02be5/result.json)
- [자동 출력 검사 상세](evidence/logs/official-example-20260921/terminal-runs/20260921T122021Z-415cd02be5/output-validation.json)
- [단계별 시간·패키지 변화·경고·GPU 사용량 검토](evidence/logs/official-example-review-20260921/stage-review.json)
- [실제 영상·GLB 관찰과 한계](evidence/logs/official-example-review-20260921/visual-review.md)
- [공식 소스 패치](evidence/logs/official-example-20260921/official-example.patch), [실행된 소스 manifest](evidence/logs/official-example-20260921/example-source-manifest.json)
- [원본 출력의 경로·크기·SHA256](output-artifacts.json), [관찰용 PNG 등 로컬 전용 파일](local-only-review-artifacts.json)

원본 결과는 `/home/minsujo/Desktop/SH/PHYSx/outputs/official-example/table-20260921T122033Z-60b5940050/pretrain/diffusion/`에 있다. `rgb.mp4`로 외형을, `description.mp4` 등으로 열지도를, `texture.glb`로 3D 결과를 볼 수 있다. 이 컴퓨터에서 만든 검토 이미지 모음은 `/home/minsujo/Desktop/SH/PHYSx/logs/official-example-review-20260921/previews-20260921T122929Z-87522300/`이다. 영상/모델/GLB/PT/PNG payload는 이 저장소에 포함하지 않는다.

## 실행 순서와 증거 구조

준비 과정의 sparse·Kaolin·renderer 검사, 고정 모델21개 다운로드/무결성 확인, FA wheel 빌드, 원본과 분리한 예제 패치 준비는 일부 병행했다. 준비가 끝난 뒤 사용자 터미널에서 FA 설치 → FA 기본 연산 → table 예제 → CPU 출력 검증을 순차 수행했고, 이어 Codex가 기록/시각 검토를 했다. 이전 단계는 [01_sparse검사](../01_sparse검사/)와 [02_renderer검사](../02_renderer검사/)에 있다.

`evidence/`는 PHYSx 루트의 상대 경로를 그대로 보존한 **기록 사본**이다. `terminal-runs/`는 상위 진행 기록이고 실제 자식 명령 로그는 `runs/`, 실제 pip 결과는 `wheel-installs/`, attention 검사 결과는 `extension-flashattn-*/`에 있다. `model-downloads/`에는 파일별 작업 기록, 상위 `model-download-receipt.json`에는 완료 파일과 해시가 있다. GPU 사용량의 원본 텍스트·시간·종료 코드·원본 해시는 [gpu-samples.json](gpu-samples.json)에 모았으며 자세한 원본 조회 폴더는 로컬에 보존했다.

FA 실패2건과 보완 빌드 성공은 `runs/*flash-attention-wheel*/` 및 `flash-attention-build/result.json`에 함께 있다. `terminal-preparation-tests/`의 fixture 실패와33개 검사 통과는 준비 코드 검사이며 GPU 실험이 아니다. 준비 문서의 `not_executed`, 빌드 receipt의 `installed_by_this_task=false`, 예제 execution의 `output_validation=pending`은 각 단계 작성 당시 상태다. 이후 완료는 터미널 최종 result와 별도 output-validation으로 확인한다. 과거 기록을 현재 상태처럼 다시 쓰지 않았다.

## 코드와 재현 입력의 범위

실제 실행 당시 `terminal_handoff.py`, `workspace_runner.py`, 설치/검사/예제/검증 helper, baseline176개와 준비 manifest, 소스·모델 receipt를 보존했다. `pip_without_site.py`, 기존 source-pins도 사본을 포함했다. `preview.condarc`는 [기존 자료보완](../../2026-09-21_자료보완/local-records/logs/install-plan-20260921/preview.condarc)에 있고 현재 로컬과 동일하다. 최신 `check_extensions.py`는 이전 renderer 단계 사본과 다르므로 이 묶음의 snapshot을 기준으로 읽는다.

소스와 모델은 Git에서 이 사본을 복사하는 것만으로 만들어지지 않는다. PhysX `4f54e750a309...`, DINO `9c7e3245797c...` 전체 고정 트리, table 입력, 작업본/pretrain 연결,21개 모델, 빌드 wheel은 각 manifest/receipt의 로컬 경로·revision·해시를 참고한다. 특히 DINO revision은 예전 source-pins에 없고 이번 `dinov2-source.json`과 준비 코드에 명시돼 있다.

`flash-attention-build/source-files.json`은 원래12,082개 소스 파일의2.5MB inventory이며 정적 wheel inspector가 읽는 입력이다. 이 파일 자체는 로컬 보관하고 `local-only-review-artifacts.json`에 경로·크기·해시를 기록했다. 새 빌드 준비 시에는 `prepare_flash_build.py`가 해당 소스 inventory를 새로 생성한다. wheel은68,360,417 bytes이며 receipt에 SHA256을 기록했다.

**이 기록을 새 컴퓨터의 성공 상태로 복사하거나 스크립트를 일괄 실행하지 않는다.** 실행기는 이 Linux 작업 경로와 과거 성공/실패 receipt를 확인하도록 설계됐다. 다른 환경의 재현 시에는 실제 설치·소스·모델 상태를 확인하고 새 실행 기록을 만들어야 한다. 이번 예제는 이미 끝났으며 다음 실제 실행은 사용자 터미널에서 별도 범위를 정한 뒤 수행한다.

## 판정의 한계

무결성 검사는 통과했지만 입력의 좁은 중앙 틈이 결과에서 큰 타원 구멍으로 나타나는 형상 차이를 관찰했다. 자동 검사는 정확한 형상·언어/물성 정답을 보장하지 않는다. 관절 그룹1개라 관절 경로와 mask 수정의 동작은 확인되지 않았다. 전체 논문 평가·재학습·반복 재현은 하지 않았다.

[evidence-manifest.json](evidence-manifest.json)은 기록 사본별 원본 절대경로·크기·SHA256을 제공한다. `.gitattributes`는 로그/patch 원문 바이트와 해시를 보존하기 위한 이 묶음 내부 설정이다. 인증정보·환경 디렉터리·캐시·큰 결과물은 게시 대상에서 제외했다.
