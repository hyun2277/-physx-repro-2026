# 2026-09-21 기본 PyTorch GPU 검사 증거

사용자 승인 후 기존 환경과 준비된 실행기를 사용한 **작은 GPU 검사 1회**의 기록이다. 추가 설치·확장 빌드·모델 다운로드·논문 실험은 수행하지 않았다. [실험일지](../../실험일지/2026-09-21_기본PyTorch_GPU검사.md)를 먼저 읽는다.

- [GPU 선택과 UUID/minor 대조](selection-and-dispatch/selection.json): 두 GPU의 조회 시점 사용률은 0%, compute 프로세스 목록은 비어 있었다. 메모리 사용량이 낮은 GPU 1을 선택했다.
- [실제 실행 명령](selection-and-dispatch/launcher-once/command.json), [종료 코드/시각](selection-and-dispatch/launcher-once/result.json): 준비된 launcher를 정확히 한 번 실행, exit0.
- [최종 상태](gpu-run/status.json), [smoke 명령/exit](gpu-run/smoke.command.json), [smoke 결과](gpu-run/smoke.stdout.log), [stderr](gpu-run/smoke.stderr.log): torch/torchvision import, 단일 GPU 식별, 작은 FP32 행렬곱·동기화·오차0, CUDA 라이브러리 경로 검사 통과.
- [전체 요약](selection-and-dispatch/summary.json): 실행 환경, 10개 내부 명령의 시각/exit, 사용량 표본 7개와 관측 최대값.
- [파일 manifest](evidence-manifest.json): 원본 상대 경로·크기·실측 SHA256. 50개 원본 로그/실행 관리 코드/요약, 합계 70,066바이트를 선별했다. 환경·캐시·모델·데이터 본체나 인증정보는 포함하지 않는다.

원본은 `PHYSx/logs/gpu-basic-check-20260921/`와 `PHYSx/logs/gpu-checks/20260921T072002Z-dfb832771cf4/`에 있다. `selection-and-dispatch/run_once.py`는 이번 실행의 GPU 선택·로그 수집·1회 실행 제어 원본이다. **검토용 사본을 다시 실행하지 않는다.** 실제 GPU 실행기와 수치 검사 소스는 기존 [준비 폴더](../../재현자료/2026-09-21_자료보완/gpu/README.md)에 있으며 실행한 해시는 `execution-attempt.json`에 기록했다.

실행기 내부 시각은 UTC(+00:00), 바깥 실행 기록과 nvidia-smi 표본 시각은 Asia/Seoul(+09:00)이다. 각 내부 명령의 `.command.json`에 실제 exit code가 있고, stdout/stderr가 분리되어 있다. 조회 실패·재시도·보호 설정 해제는 없었다.

사용량은 실행 전 1개·실행 중 5개·실행 후 1개이며 조회 시간+명목 1초 간격이다. **연속 최대값이나 우리 프로세스만의 부하가 아니다.** 사용량 표본은 전체 GPU 측정이고 PID별 GPU 메모리는 수집하지 않았다. 최초 선택 시점과 달리 연산 전 표본에 14%가 관찰됐지만, 직전 compute 조회는 비어 있었다. 해당 사용률의 원인은 확인하지 않았다.

이번 성공으로 torchvision GPU 연산, CUDA Toolkit 컴파일, source 확장, 모델 실행이나 논문 재현이 검증된 것은 아니다. 추가 실행 없이 확보한 로그만 검토했다. 최종 commit/push 결과는 `PHYSx/logs/gpu-basic-check-20260921-publication/`의 확인서와 Git 이력에서 확인한다.
