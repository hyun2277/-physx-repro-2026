# 패치 없는 원본 table 예제 실행

Codex sandbox에서는 GPU와 `example.py`를 실행하지 않는다. Linux 일반 터미널에서 아래 한 줄을 직접 실행할 때만 사전 점검과 원본 예제 실행이 시작된다.

```bash
bash /home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/실행스크립트/run_original_table_terminal.sh
```

스크립트는 고정 HEAD `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`와 tracked diff를 확인한다. `pretrain/`은 기존 체크포인트로 허용하고 삭제하지 않는다. `cache/clip/ViT-L-14.pt`와 원본 `pretrain/` 모델이 없으면 다운로드하지 않고 중단한다.

사전 점검은 물리 GPU 1만 `CUDA_VISIBLE_DEVICES=1`로 노출하고, `nvidia-smi`, GPU 1 compute-process 부재, 지정 Python의 CUDA 가용성 및 작은 행렬 계산을 확인한다. 하나라도 실패하면 `example.py`를 실행하지 않는다. GPU 0의 프로세스는 중단하지 않는다.

예제는 원본 기본 인자(`--condpath ./example/table.png`, 기본 question과 question_type)를 유지하며, `--savepath`만 새 timestamp 폴더로 지정한다. 실행 명령은 `example.py --condpath ... --savepath ...`로 기록된다. stdout/stderr/종료 코드, GPU 사용량, source·입력·모델 해시, 출력 파일 목록과 기본 `file` 결과가 `PHYSx/logs/original-example-terminal/<timestamp>/`에 계속 저장된다.

스크립트에는 설치·다운로드·Git push·GPU reset이 없다. 결과 검사는 영상·GLB·OBJ의 존재와 기본 파일 구조만 확인하며 정량평가나 논문 수치 재현을 수행하지 않는다. 결과가 생성되어도 원본 공식 예제 1건의 실행 검증으로만 해석한다.
