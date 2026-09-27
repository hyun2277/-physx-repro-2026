# 2026-09-21 작업 폴더 격리·환경 구축 증거

실험일지와 CUDA 설치 보고서를 뒷받침하는 선별 텍스트 기록이다. 과거 계획·미리보기 문서는 각 작성 시점의 상태이며 실제 설치 결과는 `result.json`, `installed-package-comparison.json`, `nvcc-version.stdout.log`를 따른다. Python 기본 패키지 결과는 별도 단계에서 기록한다.

- 원본 위치와 원본/게시본 SHA256 및 텍스트 정리는 `evidence-manifest.json`에 있다.
- 등록 경고를 포함한 CUDA 설치 출력과 실제 파일·보존 검사 결과를 포함한다.
- `workspace_isolation.py`, `isolation_probe.py`, `install_cuda_only.py`, `preview.condarc`, exact/explicit 목록은 사용한 코드·설정 기록이다. 컴퓨터별 절대경로를 검토해야 하며 문서를 일괄 실행하지 않는다. 재실행 시 기존 prefix는 덮어쓰지 않고 중단한다.
- 원본 터미널 전체 로그(약131MB), 전체 환경변수/인증 설정, 환경 디렉터리·wheel·Conda archive·캐시·모델·데이터는 포함하지 않았다. `HF_TOKEN_PATH` 같은 변수명/파일 경로는 설정 설명이며 토큰 값이 아니다.
- 일부 복사 문서의 로컬 전용 링크는 클릭 링크 대신 원래 경로로 표시했다. 설치 stdout의 터미널 제어문자·빈 줄만 정리했고 원본 전체 로그는 PHYSx/logs에 보존했다.
- 설치·파일·버전 확인을 CUDA 컴파일·모델 실행·GPU 연산 검증으로 해석하지 않는다.
