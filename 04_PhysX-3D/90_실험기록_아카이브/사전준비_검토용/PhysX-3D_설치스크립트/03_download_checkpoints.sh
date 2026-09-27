#!/bin/bash
# 체크포인트 다운로드 — download_pretrain.sh와 동일한 두 저장소/경로, 명령만 최신 CLI로 교체.
# 실행 전제: PhysX-3D 폴더 안, conda activate physxgen 상태.
#
# 2026-09-21 수정: `huggingface-cli`가 신형 huggingface_hub(1.x)에서 완전히 제거됐음을 실제
# 명령 실행으로 확인함(PhysX-3D_Claude_독립검증.md §9) — 이 개발 머신에 이미 설치돼 있던
# huggingface_hub 1.11.0으로 `huggingface-cli whoami`를 실행하면
# "Warning: `huggingface-cli` is deprecated and no longer works. Use `hf` instead." 출력과 함께
# `huggingface-cli download ...`는 exit code 1로 실패한다. 신형 `hf download` CLI로 교체한다
# (`hf download --help`로 옵션 직접 확인: REPO_ID [FILENAMES]..., --local-dir 옵션은 기존과
# 동일하게 동작).
#
# 총 용량 참고(2026-09-20 HuggingFace API로 직접 확인): Caoza/PhysXGen 저장소 자체가 약 9GB.
# TRELLIS-image-large는 별도(수 GB 추가 예상, 정확한 용량은 다운로드 시점에 확인). 디스크 여유
# 20GB 이상 권장.
set -euo pipefail

if [ ! -f "./setup.sh" ]; then
  echo "[중단] 현재 디렉터리가 PhysX-3D 저장소 루트가 아닌 것 같습니다(setup.sh 없음)." >&2
  echo "        cd PhysX-3D 후 다시 실행하세요." >&2
  exit 1
fi

if ! command -v hf >/dev/null 2>&1; then
  echo "[중단] 'hf' 명령을 찾을 수 없습니다. huggingface_hub가 설치돼 있는지 확인하세요" >&2
  echo "        (pip install -U huggingface_hub, 또는 02_install_deps.sh의 --basic에 포함돼 있어야 함)." >&2
  exit 1
fi

TS=$(date +%Y%m%d_%H%M%S)
LOGDIR="./logs"
mkdir -p "$LOGDIR"

{
  echo "=== hf 로그인 상태 확인 (게이트 모델은 아니지만 확인 차) ==="
  hf auth whoami 2>&1 || echo "(로그인 안 돼 있어도 이 두 저장소는 공개(gated 아님)라 보통 문제 없음)"

  echo
  echo "=== [1/2] TRELLIS-image-large 다운로드 ==="
  hf download microsoft/TRELLIS-image-large --local-dir pretrain/trellis

  echo
  echo "=== [2/2] PhysXGen(diffusion+vae 체크포인트) 다운로드 ==="
  hf download Caoza/PhysXGen --local-dir pretrain

  echo
  echo "=== 다운로드 결과 확인 ==="
  echo "--- pretrain/diffusion (example.py가 실제로 로드하는 경로) ---"
  find pretrain/diffusion -type f 2>&1
  echo "--- pretrain/trellis ---"
  du -sh pretrain/trellis 2>&1
  echo "--- 전체 pretrain 용량 ---"
  du -sh pretrain 2>&1

} 2>&1 | tee "$LOGDIR/03_download_checkpoints_${TS}.log"

echo "완료. 다음: 04_run_example.sh 실행"
