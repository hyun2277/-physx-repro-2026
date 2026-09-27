#!/bin/bash
# 저자 제공 기본 예제(example/table.png, example/chair.png)로 첫 스모크 테스트.
# 실행 전제: PhysX-3D 폴더 안, conda activate physxgen 상태, 체크포인트 다운로드 완료.
#
# 기존 프로젝트 관례대로 GPU 사용률을 1초 간격 CSV로 백그라운드 기록 — PhysX-3D의 실제 VRAM
# 사용량이 아직 미확인 상태라(TRELLIS 공식 문서의 "16GB 이상" 최소치만 알려져 있음), 이 로그가
# 그 수치를 실측으로 검증하는 근거가 됨.
#
# 2026-09-21 수정: 출력 폴더에 타임스탬프를 넣어 재실행 시 이전 결과를 덮어쓰지 않도록 변경
# (이전 버전은 ./outputs_vis/table, ./outputs_vis/chair 고정 경로라 재실행하면 덮어썼음 —
# PhysX-3D_Claude_독립검증.md §5).
set -euo pipefail

if [ ! -f "./setup.sh" ]; then
  echo "[중단] 현재 디렉터리가 PhysX-3D 저장소 루트가 아닌 것 같습니다(setup.sh 없음)." >&2
  echo "        cd PhysX-3D 후 다시 실행하세요." >&2
  exit 1
fi

TS=$(date +%Y%m%d_%H%M%S)
LOGDIR="./logs"
mkdir -p "$LOGDIR"
OUT_TABLE="./outputs_vis/table_${TS}"
OUT_CHAIR="./outputs_vis/chair_${TS}"

echo "=== GPU 사용률 백그라운드 기록 시작 ==="
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,clocks.sm \
  --format=csv -l 1 > "$LOGDIR/gpu_log_example_${TS}.csv" &
GPU_LOG_PID=$!
echo "GPU 로그 PID: $GPU_LOG_PID"

cleanup() {
  echo "GPU 로그 프로세스 종료 (PID $GPU_LOG_PID)"
  kill "$GPU_LOG_PID" 2>/dev/null || true
}
trap cleanup EXIT

{
  echo "=== 실행 직전 정보 ==="
  echo "git commit: $(git rev-parse HEAD)"
  date

  echo
  echo "=== table.png (기본값) -> $OUT_TABLE ==="
  python example.py --condpath ./example/table.png --savepath "$OUT_TABLE" --question "wooden tabletop surface" --question_type 0

  echo
  echo "=== chair.png -> $OUT_CHAIR ==="
  python example.py --condpath ./example/chair.png --savepath "$OUT_CHAIR" --question "cushioned seat surface" --question_type 0

  echo
  echo "=== 결과물 확인 ==="
  find "$OUT_TABLE" "$OUT_CHAIR" -type f

} 2>&1 | tee "$LOGDIR/04_run_example_${TS}.log"

echo "완료. $OUT_TABLE / $OUT_CHAIR 안에 rgb.mp4, affordance.mp4, material.mp4, description.mp4,
texture.glb 등이 있으면 성공. kinematic.obj/kinematic_child.mp4/kinematic_parent.mp4는 모델이
물체에 관절 그룹이 2개 이상 있다고 판단했을 때만 생성됨(코드상 num_group==1이면 콘솔에
'fixed object'만 찍히고 이 파일들은 안 만들어짐) — table.png/chair.png가 실제로 어느 쪽으로
나올지는 실행 전엔 확인 불가, 로그 콘솔 출력으로 직접 확인할 것.
주의(공식 코드 버그, PhysX-3D_Claude_독립검증.md §7): 관절이 있는 것으로 판단된 경우 콘솔에
찍히는 'kinematic type' 판정은 example.py 211~212행의 인덱싱 버그 영향을 받을 수 있다 — 이
버그가 실제 출력값에 어느 정도 영향을 주는지는 5090 실기 없이는 확정 불가.
관절이 확실히 있는 물체(노트북 등) 테스트는 05_run_custom_image.sh로 진행."
