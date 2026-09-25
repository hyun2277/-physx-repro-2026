# 29354 사전학습 inference 사전검사

이번 단계는 conditioning PNG 한 장을 공식 `example.py`에 넣는 실행을 계획했으나, 실행 전 필수 보호 규칙에 의해 중단했다. 고정 source HEAD는 `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`였지만, source working tree에 추적 파일 변경이 남아 있었다. 변경 파일은 `trellis/**/__pycache__/*.pyc` 자동 생성 바이트코드이며, 사용자 규칙상 추적 변경이 하나라도 있으면 `example.py`를 실행하지 않는다. untracked `pretrain/`은 보존했고 건드리지 않았다.

최신 conditioning 결과의 `transforms.json`에는 24개 frame과 대응 PNG가 모두 존재한다. 모든 frame의 경로와 4x4 유한 camera transform을 검증한 뒤, 임의 선택이 아니라 가장 낮은 유효 frame index인 `000.png`을 선택 대상으로 기록했다. 선택 transform과 PNG SHA256은 실행 로그 `logs/inference-29354/<run_id>/selection.log`에 남겼다.

따라서 이번 단계의 `example.py` 종료 코드·GPU 사용량·출력 파일은 생성되지 않았다. 먼저 source의 추적 pyc 변경을 별도 정리해 보호 검사를 통과시킨 뒤에야 GPU 1 실행을 재검토할 수 있다. 논문 정량평가나 정확도 검증을 의미하지 않는다.
