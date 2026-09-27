# 기본 Python 패키지 설치 결과

**설치 성공:** 지정 `envs/physxgen`에 검토한 기본 wheel169개를 설치했다. 기존 pip26.2.1을 포함한 최종 배포판170개가 기대 집합과 정확히 같고, torch2.7.1+cu128 / torchvision0.22.1+cu128을 확인했다. pip check는 exit0, `No broken requirements found.`였다.

## 설치 전 대조와 범위

기존 hash고정 foundation lock을 변경하지 않았다. sparse 후보 spconv/cumm 및 FlashAttention·xformers·CLIP·utils3d·renderers·vox2seq 소스 패키지를 포함하지 않았다. 모든 대상은 미리 빌드된 wheel이다. Kaolin은 검토한 torch2.7.1/cu128용 wheel이며 source build를 수행하지 않았다.

저장된 metadata에서 foundation169개만 대상으로 현재 Linux/Python3.10.21의 활성 기본 의존성267개를 확인했고 충돌0이었다. `pip download --no-index --only-binary=:all: --require-hashes`로 원본 lock의 직접 URL만 사용해 PHYSx/cache/python-foundation-wheels-20260921에 wheel을 확보했다. 패키지 다운로드는 모델 다운로드가 아니다. 실제 wheel169개의 SHA256을 직접 계산해 lock과 대조하고, 실제 METADATA의 이름/버전/Requires-Dist를 기존 보고서와 비교했다. 같은267개 활성 의존성은 누락/충돌0이었다.

각 wheel의 정확한 file:// 경로와 SHA256으로 로컬 lock을 만들었다. 로컬 자료만 사용하는 install --dry-run --ignore-installed 결과는169개 모두 같은버전/해시/경로였다. URL이 작업 폴더의 해당 wheel과 다르면 설치 전에 중단하도록 했다. 실제 설치도 동일 로컬 lock과 --no-index/--only-binary/--require-hashes/--no-compile을 사용했다. --report 파일은 설치 전 계획 단계에서 생성될 수 있으므로 성공 근거로 단독 사용하지 않았고, 실제 종료코드와 설치 후 배포판 집합 및 pip check를 함께 확인했다.

## 격리·실행 결과

검토한 workspace_isolation.py를 그대로 사용했다. 외부 읽기 전용과 PHYSx 내부 cache/tmp/logs, GPU장치 비노출을 확인한 후 실행했다. -I -B -S 및 전용 pip bootstrap으로 .pth/sitecustomize 코드를 실행하지 않았다. 실제 wheel 내 startup 파일 목록은 정적으로만 기록했다. source build와 Python bytecode compile을 수행하지 않았으며 torch 등 모델 패키지를 import하지 않았다.

- wheel download: 05:01:29–05:09:03(+09:00), exit0.
- 실제 설치: 05:09:13–05:10:03(+09:00), exit0.
- 최종 단계 완료: 05:10:04(+09:00).
- 설치 후 pip check: exit0.

## 버전 변화와 보존

기존 target환경에서 packaging26.3→24.2, setuptools83.0.0→75.8.0, wheel0.47.0→0.45.1은 검토한 계획대로 바뀌었다. pip26.2.1은 그대로다. Conda metadata는 pip 교체 전 이력이며 실제 Python 배포판 버전은 dist-info로 판정했다.

Anaconda base metadata, 전용 CUDA Toolkit metadata와 기존에 확인한 실제 파일 hash, 시스템 CUDA 링크/NVCC, dpkg 상태, 드라이버 버전 텍스트와 기존 검토 입력 hash가 동일했다. Toolkit 전체 파일을 전수 hash한 검사라고 표현하지 않는다. 별도로 승인된 기록 저장소 문서 작성은 같은 시기에 진행했다.

## 로그와 남은 문제

- [설치 결과](result.json), [실제 버전](installed-versions.json), [보존 검사](preservation.json)
- [실제 wheel 의존성](downloaded-dependencies.json), [로컬 미리보기 비교](offline-preview-comparison.json)
- [설치 전체 stdout](install-foundation.stdout.log), [설치 stderr](install-foundation.stderr.log), [설치 명령](install-foundation.command.json)
- [pip check 출력](pip-check.stdout.log), [pip check 명령·종료코드](pip-check.command.json)

미설치 source 확장·CLIP/utils3d, spconv/cumm RTX5090 경로, 바이너리 ABI와 GPU 실제 연산은 별도 검증 대상이다. CLIP 경로 패치도 실제 소스에 미적용 상태다. 이번에는 모델 다운로드·추론·학습·GPU 연산을 하지 않았다.
