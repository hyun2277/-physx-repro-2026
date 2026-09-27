# 2026-09-21 기본 Python 패키지 설치 증거

기본169개 wheel 설치와 실제 버전·pip check 결과를 기록한다. 전체 상태는 `result.json`, 상세 결과는 `summary.md`를 참고한다. CUDA/source 확장 빌드나 GPU 연산은 수행하지 않았다.

- 169개 실제 wheel의 SHA256을 lock과 대조했고 실제 METADATA의 활성 기본 의존성267개를 검사했다. 기본 목록과 설치 전 오프라인 미리보기의 차이는0이었다.
- 실제 설치된 배포판170개는 foundation169개와 기존 pip26.2.1이다. 기존 target환경의 packaging/setuptools/wheel downgrade는 검토된 pin을 따른 변화다.
- `python-resolved.constraints.txt`에 sparse후보2개가 남아 있어도 constraints는 설치요청이 아니며 이번 foundation lock/결과에는 포함되지 않는다.
- `install_foundation.py`와 `pip_without_site.py`는 이번에 사용한 실행 기록이다. 해당 컴퓨터 절대경로 및 준비로그에 의존하므로 그대로 일괄 재실행하지 않는다.
- 원본 위치와 텍스트 파일 SHA256은 `evidence-manifest.json`에 있다. 대형다운로드로그, 전체환경설정, 실제wheel/cache/env/model/data 및 인증정보는 포함하지 않았다.
- 바이너리 import·ABI·GPU호환성은 이 metadata/설치검사로 검증되지 않는다.
