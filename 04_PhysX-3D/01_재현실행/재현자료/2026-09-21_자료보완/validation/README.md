# 이번 자료 보완의 검증 증거

원본 실행별 기록은 `PHYSx/logs/repro-materials-20260921/`에 있다. 이 폴더에는 공개 전 검토한 stdout/stderr/command/result와 원본 경로·SHA256을 선별한다. 설치·GPU 실행 증거가 아니다.

- `verify-materials`: 이 자료 묶음의 SHA256/크기와 foundation 필수 파일 검사.
- `static-audit`: Linux 원본과 사본 대조, Python AST·JSON 문법, 문서 상대 링크, 입력 hash, 비밀 패턴 및 Git 변경 범위 검사. 과거 실행기를 실행하지 않는다.
- `gpu-plan`: 지정 Python을 `-I -B -S`로 시작해 GPU 실행기의 계획 JSON만 출력.
- `gpu-plan-mock-tests`: 가짜 UUID·mock·순수 함수로 경계/오류 기록을 검사. 실제 GPU나 NVIDIA 명령을 호출하지 않는다.

각 결과의 exit code와 stdout/stderr를 함께 읽는다. 정적 검사와 모의 검사 성공은 실제 namespace·라이브러리 import·CUDA 연산 성공을 뜻하지 않는다. 현재 GPU 실행 및 사용량 측정은 미실행이다.

상위 `materials-manifest.json`은 원본 사본·안내·코드의 무결성을 검사한다. 순환 hash를 피하기 위해 manifest 자신과 이 validation 폴더는 대상에서 제외한다. 이 폴더의 선별 로그는 `evidence-manifest.json`으로 크기/SHA256/원본 위치를 별도 기록한다. Windows에서 실제 Python 검증기를 실행한 결과는 아직 없다.
