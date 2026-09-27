# 29354 pretrained inference GPU 사전검사

최신 source clean 검사에서 고정 HEAD `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`와 허용된 `trellis/**/__pycache__/*.pyc` 변경만 확인했다. conditioning 입력 `000.png`과 `transforms.json` hash, 기존 `pretrain/diffusion` checkpoint inventory도 기록했다.

실제 실행 직전 `nvidia-smi --query-compute-apps=pid,gpu_uuid,used_memory --format=csv,noheader,nounits`가 NVIDIA driver와 통신하지 못하고 종료 코드 9를 반환했다. 따라서 GPU 1 보호 상태를 확인할 수 없어 보호 규칙에 따라 `example.py`를 실행하지 않았다. 같은 명령을 반복하지 않았고, 영상·GLB도 생성되지 않았다.

로그: `/home/minsujo/Desktop/SH/PHYSx/logs/inference-29354/20260925T191000Z/`. 이번 기록은 inference 성공이나 논문 정량평가를 의미하지 않는다.
