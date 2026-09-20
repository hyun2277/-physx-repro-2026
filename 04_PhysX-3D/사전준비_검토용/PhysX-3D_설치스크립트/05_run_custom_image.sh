#!/bin/bash
# 임의 이미지(예: 노트북, 로봇팔)로 테스트하는 템플릿.
# 사용법: bash 05_run_custom_image.sh /path/to/my_image.jpg
#
# 참고(계획 문서 §1-1에서 확인한 내용): --question/--question_type은 관절 타입 판정과 무관한
# 시각화 옵션일 뿐이다. 관절 타입 판정 결과는 콘솔 출력의 "kinematic type: ..." 줄로 확인한다
# (A. No movement constraints / B. Prismatic joints / C. Revolute joints / D. Hinge joint /
# E. Rigid joint 중 하나 — 논문이 정의한 5분류, urdformer 때와 달리 노트북 힌지 같은 개념이
# 실제로 이 모델의 출력 어휘 안에 있음).
#
# 중요(공식 코드 버그, PhysX-3D_Claude_독립검증.md §7 / Codex 대조메모 1번): 아래에서 grep으로
# 뽑아주는 'kinematic type' 값은 example.py 211~212행(행/열 인덱싱 버그)과 207행(부모 그룹
# 임계값 계산의 팬시 인덱싱 버그) 둘 다의 영향을 받을 수 있다. 이 스크립트는 그 값을 "참고용
# 출력"으로만 취급할 것 — 실제로 맞는 값인지는 5090에서 실기 검증 전까지 보장 못 한다
# (같은 폴더의 PhysX-3D_공식코드_패치/ 안에 211~212행만 기계적으로 고친 패치가 있음, 207행은
# 별도 설계 판단이 필요해 패치하지 않음).
#
# 2026-09-21 수정: 출력 폴더에 타임스탬프를 넣어 재실행 시 이전 결과를 덮어쓰지 않도록 변경.
set -euo pipefail

if [ ! -f "./setup.sh" ]; then
  echo "[중단] 현재 디렉터리가 PhysX-3D 저장소 루트가 아닌 것 같습니다(setup.sh 없음)." >&2
  echo "        cd PhysX-3D 후 다시 실행하세요." >&2
  exit 1
fi

if [ $# -lt 1 ]; then
  echo "사용법: bash 05_run_custom_image.sh /path/to/image.jpg [질문 문구]"
  echo "예: bash 05_run_custom_image.sh ./my_images/laptop.jpg \"hinged screen that opens and closes\""
  exit 1
fi

IMG_PATH="$1"
QUESTION="${2:-a functional part of this object}"
IMG_NAME=$(basename "$IMG_PATH" | sed 's/\.[^.]*$//')
TS=$(date +%Y%m%d_%H%M%S)
LOGDIR="./logs"
mkdir -p "$LOGDIR"
OUT_DIR="./outputs_vis/${IMG_NAME}_${TS}"

echo "=== GPU 사용률 백그라운드 기록 시작 ==="
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,clocks.sm \
  --format=csv -l 1 > "$LOGDIR/gpu_log_${IMG_NAME}_${TS}.csv" &
GPU_LOG_PID=$!
cleanup() { kill "$GPU_LOG_PID" 2>/dev/null || true; }
trap cleanup EXIT

{
  echo "입력 이미지: $IMG_PATH"
  echo "질문 문구(시각화용, 관절 판정과 무관): $QUESTION"
  echo "git commit: $(git rev-parse HEAD)"
  date

  python example.py \
    --condpath "$IMG_PATH" \
    --savepath "$OUT_DIR" \
    --question "$QUESTION" \
    --question_type 2

  echo
  echo "=== 결과물 ==="
  find "$OUT_DIR" -type f

} 2>&1 | tee "$LOGDIR/05_run_custom_${IMG_NAME}_${TS}.log"

echo
echo "확인할 것: 위 로그에서 'kinematic type: ...' 줄을 grep으로 찾아서 어느 카테고리로 판정됐는지
확인. 노트북 사진이면 'C. Revolute joints'가 나오는지가 핵심 관찰 포인트 — 단, 이 값 자체가
공식 코드 버그(위 주석 참고)의 영향을 받을 수 있으므로 '기대한 답이 나왔다'만으로 파이프라인이
전부 정상이라고 단정하지 말 것."
grep -A1 "kinematic type" "$LOGDIR/05_run_custom_${IMG_NAME}_${TS}.log" || echo "(kinematic type 출력 없음 = 모델이 이 물체를 고정된(fixed) 물체로 판단했다는 뜻)"
