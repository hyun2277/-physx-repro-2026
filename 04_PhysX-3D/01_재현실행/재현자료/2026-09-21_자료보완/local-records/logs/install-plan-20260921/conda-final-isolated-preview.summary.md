# 보완된 격리 조건의 Conda 설치 미리보기

- 기록 시각: 2026-09-21T04:36:10.943440+09:00
- 범위: CUDA Toolkit 전용 prefix에 대한 설치 미리보기만 수행했다. 실제 설치·빌드·GPU 실험·모델 다운로드는 하지 않았다. Python 의존성 조회도 반복하지 않았다.
- 결과: exit_code=0, success=True, dry_run=True, 전체 확인 통과=True.
- 비교: 기존 exact spec118개 및 이전 LINK118개와 새 LINK118개를 (name, version, build)로 대조했다. 추가0, 제거0, 버전/build 변경0, channel 변경0개. UNLINK=0.
- FETCH 계획: 기존 97개/2100106977 bytes → 이번 97개/2100106977 bytes. 이것은 예상값이며 실제 전송량·설치 크기가 아니다.
- stderr 크기: 0 bytes.

## 실행 조건과 파일

`workspace_isolation.py`를 그대로 사용했다. 외부 파일시스템은 읽기 전용이며 PHYSx에만 지속적인 파일 쓰기를 허용한다. 다운로드/캐시/임시 경로는 PHYSx 내부이고 /tmp, /var/tmp, /dev/shm도 작업 폴더에 연결된다. HOME은 바꾸지 않는다. `--clearenv`, `--no-default-packages`, `--copy`, 정확한 118개 version/build 및 명시적 공식 channels를 적용했다. 명령 전체는 비교 JSON의 command_inside_workspace_isolation 배열에 보존했다. 인증정보·전체 환경변수는 기록하지 않았다.

처음에는 도구 샌드박스가 bwrap namespace 생성을 차단하여 exit1이었고 Conda는 시작되지 않았다. 명령별 실행 승인 후 동일한 bwrap 격리를 유지하여 재시도했다. 시스템 보호 설정을 바꾸지 않았다.

- 실제 solver 출력: [conda-final-isolated-preview.json](conda-final-isolated-preview.json)
- stderr: [conda-final-isolated-preview.stderr.log](conda-final-isolated-preview.stderr.log)
- 실행 시작/종료 및 exit code: [conda-final-isolated-preview.execution.log](conda-final-isolated-preview.execution.log)
- 실행 전 상태: [conda-final-isolated-preview.before.json](conda-final-isolated-preview.before.json)
- 구조화된 비교/보존 확인: [conda-final-isolated-preview.comparison.json](conda-final-isolated-preview.comparison.json)

## 보존 확인

Toolkit prefix는 여전히 없다. 지정 envs/physxgen의 배포판4개와 Conda 기록32개가 그대로이며 conda-meta의 모든 파일/history 해시도 변하지 않았다. 시스템 CUDA 링크는 기존 /usr/local/cuda-12.2이며 기록 저장소는 clean이다. 실행기·Conda 설정·기존 고정 목록·이전 solver 보고서·Python lock/constraints 파일 해시도 모두 변하지 않았다. 캐시 메타데이터와 이번 logs 파일 작성은 허용 범위의 변화다.

## 남은 문제

이번 성공은 새 격리 조건의 의존성 해결 성공만 뜻한다. 실제 Conda create에서 읽기 전용 HOME 등록 경고가 발생해도 완료되는지, --copy의 설치 결과, 실제 NVCC/헤더/라이브러리 및 host compiler 동작은 아직 확인하지 않았다. Python/source 패키지 설치·확장 빌드·RTX5090 GPU 연산 호환성도 미검증이다. CLIP 검토용 패치는 첫 CLIP 가중치 다운로드/load 전에 실제 작업 소스에 적용해야 한다.

## 다음 한 단계

사용자가 실제 설치를 지시하면 기존 계획의 명령으로 **작업 폴더 전용 CUDA Toolkit만 설치**한다. Python 패키지/source 빌드/GPU 실험을 함께 진행하지 않는다. 이번 요청에서는 그 설치를 실행하지 않았다.
