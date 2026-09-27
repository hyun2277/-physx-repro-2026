# 설치 계획 재검토 기록

날짜: 2026-09-21, Asia/Seoul. 대상: `installation-plan.md`의 설치 격리와 CLIP 경로.

## 수행 범위

기존 계획·로컬 도구 소스·고정된 공개 소스를 읽고 계획서와 검토용 helper/diff를 작성했다. Python 표준 라이브러리와 기존 bwrap으로 파일 경로/마운트 동작만 검사했다. **패키지 설치·삭제·업데이트, CUDA/source 빌드, GPU 실험, 모델 다운로드는 수행하지 않았다.** 기존 설치 스크립트를 실행하지 않았고 apt/autoremove, 전역 설정 변경, 보호 설정 변경도 하지 않았다. 이번에는 Conda/Pip 의존성 미리보기도 다시 실행하지 않았다.

기존 계획은 `installation-plan.before-isolation-review.md`에 보존했다. 이전 `final-verification.json`, `artifact-sha256.json`은 당시 기록으로 남기고 이번 결과는 별도 파일명으로 저장했다.

## 발견한 문제와 반영 내용

1. 이전의 대화형 bwrap 셸 뒤에 환경변수를 수동 설정하는 방식은 실패 후 원래 셸에서 명령을 실행할 여지가 있었다. 모든 미래 명령을 `workspace_isolation.py`가 직접 실행하도록 바꿨다. bwrap 실행 환경 자체도 최소값만 전달하며, 내부는 `--clearenv`와 명시적 허용 목록을 사용한다. 셸 초기화 파일을 읽지 않는다.
2. 기존 `CONDARC` 지정은 Conda23.3.1의 다른 config 읽기를 모두 끄지 않는다. 미래 create/preview에 `--no-default-packages`와 `--copy`를 추가했다. 이 두 옵션을 포함한 새 격리 preview는 **아직 실행하지 않았다**. 정확한 패키지/대상 대조를 설치 전 조건으로 명시했다. HOME 등록 파일은 바꿀 수 없으므로 읽기 전용으로 두며, 실제 설치의 경고/성공 여부는 설치 후 확인 대상이다.
3. 외부 파일시스템은 읽기 전용, PHYSx만 쓰기 가능하게 연결했다. `/tmp`와 `/var/tmp`는 PHYSx/tmp, `/dev/shm`은 PHYSx/tmp/shm에 연결했다. HOME은 변경하지 않는다. 알려진 캐시 변수, HF 동적 모듈/토큰 경로, XDG 계열, Triton dump/override도 PHYSx 내부로 지정했다. 상속된 캐시/컴파일러/Git/셸 관련 설정은 허용 목록 밖에 둔다.
4. Git의 사용자 hook/template 영향을 막도록 사용자·시스템 config를 읽지 않고 빈 작업 폴더 내 template와 `core.hooksPath=/dev/null`을 유지한다. 기존 소스/Toolkit 대상이 있으면 중단하도록 별도의 `test` 명령을 배치했다. source 설치는 고정된 빌드 의존성을 사용하고 `--no-deps`로 추가 자동 의존성 선택을 막도록 계획했다.
5. OpenAI CLIP은 XDG/TORCH_HOME 설정만으로 다운로드 경로가 바뀌지 않는다. PhysX 두 호출에 `download_root=os.environ["PHYSX_CLIP_DOWNLOAD_ROOT"]`를 넣는 **미적용 검토용 patch**를 작성했다. 변수가 없으면 실패하며 HOME fallback을 추가하지 않았다. 세 원문 파일을 공개 고정 SHA에서 logs 아래 읽기용 `.review.txt`로 저장했다. 소스 AST 파싱/추가 인자 외 AST 변경 없음/메모리 내 diff 재적용 대조를 수행했으며, 실제 소스 `git apply`나 CLIP import/load는 하지 않았다.
6. CLIP ViT-L/14의 공식 URL에 있는 예상 SHA256을 기록했다. 모델 파일 자체를 받지 않았으므로 실측 해시 검증이라고 표현하지 않았다. 버전 선택 근거, 미래 실제 설치 명령, 설치 전 문제, 설치 직후 및 별도 GPU 단계의 확인 기준을 계획서에서 분리했다.
7. 독립 읽기 전용 검토에서 로그용 process substitution의 tee 실패가 상위 셸에 전달되지 않을 수 있다는 점을 확인했다. 미래 명령은 로그 파일에 직접 리다이렉션하도록 고쳐 로그 open 실패 시 설치 전에 멈추게 했다. Bash 문법 검사도 바깥 명령과 heredoc 안의 명령을 각각 파싱한다.

## 격리 검사 과정과 한계

- 기존 단순 bwrap 방식은 `/bin/true` 실행만 성공했다. 이것만으로 파일 경로 보호가 검증됐다고 판단하지 않았다.
- 강화한 실행기의 첫 namespace 생성은 도구 샌드박스 안에서 `No permissions to create new namespace` 오류로 실패했다. 명령별 샌드박스 밖 실행 승인을 통해 다시 실행했으며, OS 보호 설정/namespace 정책은 변경하지 않았다.
- 승인 후 실행된 최초 probe는 외부 마운트 읽기 전용 및 임시 파일 연결 확인을 통과한 뒤, 외부 쓰기 핸들 오류를 EROFS로만 예상한 assertion에서 실패했다. 실제 오류는 EACCES(errno13)였다. 검사 코드를 수정해 오류명을 사실대로 남기고, 쓰기 핸들 거부와 별도 statvfs 읽기 전용 확인을 모두 요구하도록 했다. 파일은 O_TRUNC 없이 열기만 시도했으며 외부에 내용을 쓰지 않았다.
- 수정된 최종 probe는 exit0이었다. 최종 실행기와 캐시 변수 검사를 반영한 결과는 `isolation-probe-result.json`에 있다. 검사 표식 파일은 PHYSx/tmp 및 그 shm 하위에만 생성했고, 생성한 표식만 자동으로 닫고 정리했다.
- 검사한 외부 마운트: `/usr/local`, `/usr/local/cuda-12.2`, `/home/minsujo`, `/home/minsujo/anaconda3`, `/etc`, `/proc/sys`. GPU 장치 경로는 보이지 않았다. Git hook 경로와 HOME 보존을 확인했다. 결과 JSON에 기록된 변수는 캐시/임시 경로 허용 목록뿐이며 인증정보나 전체 환경변수는 수집하지 않았다.
- 부모 환경에 표식 변수를 주입해 모든 상속 상황을 시험한 것은 아니다. 최종 자식 환경에서 지정 변수의 부재를 확인했고, 차단 방식은 코드로 검토했다. 임의의 모든 패키지/빌드 backend에 대한 파일 접근 검증이나 악성 코드 보안 감사가 아니다.
- **Conda 등록 경고를 포함한 실제 전체 설치 성공, CUDA compiler 동작, source 빌드, GPU 호환성은 여전히 미검증이다.** 미래 GPU 검증에는 장치를 제공하는 별도 실행 방식이 필요하며, 설치용 helper에서 무작정 GPU 장치 보호를 풀지 않는다.

## 산출물과 보존 확인

- 최종 계획: `installation-plan.md`
- 격리 실행기/최소 검사: `workspace_isolation.py`, `isolation_probe.py`
- 격리 검사 결과: `isolation-probe-result.json`
- CLIP 검토용 diff/정적 검증: `clip-cache-path.review.patch`, `clip-cache-review.json`
- 읽기 전용 환경 대조 및 Bash/Python 문법 검사: `isolation-review-verification.json`
- 이번 파일 SHA256 목록: `isolation-review-sha256.json`

지정 환경의 배포판/Conda 기록은 이전 inventory와 대조하고, Toolkit prefix 부재·시스템 CUDA 링크·기록 저장소 상태·기존 lock/보고서 해시를 확인한다. 결과는 위 검증 JSON에 기록한다. 후속 실행 승인은 이번 문서 보완 요청에 포함된 것으로 해석하지 않는다.
