#!/bin/bash
# PhysX-3D 착수 전 환경 스냅샷 — 지금까지 다른 논문들과 동일한 로깅 관례.
# 5090 Linux 머신에서 실행. 로그는 이 스크립트가 있는 폴더 기준 logs/ 밑에 쌓입니다.
set -uo pipefail

TS=$(date +%Y%m%d_%H%M%S)
LOGDIR="./logs"
mkdir -p "$LOGDIR"

echo "=== nvidia-smi 전체 사양 ==="
nvidia-smi -q > "$LOGDIR/gpu_spec_before_${TS}.txt" 2>&1
cat "$LOGDIR/gpu_spec_before_${TS}.txt" | head -30

echo
echo "=== nvcc 버전(있다면) ==="
nvcc --version 2>&1 | tee "$LOGDIR/nvcc_version_${TS}.txt"

echo
echo "=== python 버전(현재 셸 기준, conda 환경 만들기 전) ==="
python --version 2>&1 | tee "$LOGDIR/python_version_before_${TS}.txt"

echo
echo "=== OS/커널 ==="
uname -a 2>&1 | tee "$LOGDIR/uname_${TS}.txt"

echo
echo "=== 여유 디스크 용량 (체크포인트 다운로드가 총 10GB+ 예상되므로 미리 확인) ==="
df -h . 2>&1 | tee "$LOGDIR/disk_space_${TS}.txt"

echo
echo "스냅샷 완료 → $LOGDIR/ 에 저장됨"
