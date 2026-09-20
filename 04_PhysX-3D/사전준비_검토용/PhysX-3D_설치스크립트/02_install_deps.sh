#!/bin/bash
# PhysX-3D 나머지 의존성 설치.
# 실행 전제: PhysX-3D 폴더 안에서, conda activate physxgen 상태로 실행.
#
# 2026-09-21 Codex 대조메모 반영 수정본(이전 버전 대비 변경점):
#   1. --vox2seq 플래그 제거 — 공식 setup.sh 238행이 `cp -r extensions/vox2seq ...`를 실행하는데
#      저장소에 extensions/ 폴더 자체가 없어(직접 ls로 확인) 이 단계가 실패하고, `. ./setup.sh`가
#      source(현재 셸)로 실행되는 데다 set -euo pipefail이 켜져 있어 이후 kaolin/xformers/clip/
#      ipdb 설치가 전부 스킵되는 것까지 직접 확인함(PhysX-3D_Claude_독립검증.md §1). 대신 실제
#      루트 경로(vox2seq/)를 명시적으로 잡아 수동 설치.
#   2. xformers를 기본적으로 생략(skip-by-default)하도록 변경 — xformers 0.0.35의 PyPI 의존성이
#      torch>=2.10이라(PyPI 메타데이터로 직접 확인), 01에서 고정한 torch==2.7.1 위에 무작정
#      `pip install xformers`를 돌리면 pip 리졸버가 torch를 끌어올릴 위험이 있음. `--no-deps`는
#      이 위험만 막을 뿐 ABI/wheel 호환성 자체를 보장하지 않는다는 지적(Codex 대조메모 3번)을
#      반영해, "--no-deps로 강행"이 아니라 "필요 없으면 생략"을 기본값으로 삼는다. 실제 기본
#      attention 백엔드는 flash_attn이므로(trellis/modules/attention/__init__.py 3행,
#      BACKEND='flash_attn', 직접 확인) xformers 없이도 example.py는 동작한다.
#   3. import 검증에 flash_attn·vox2seq·diffoctreerast·mip-splatting(rasterizer)을 추가 —
#      이전 버전은 torch/clip/kaolin/xformers/spconv/nvdiffrast만 확인해 실제 기본 백엔드
#      성공 여부를 검증하지 않았음(Claude_독립검증 §3).
#   4. 실행 폴더 가드 추가(PhysX-3D 폴더 안이 아니면 즉시 중단) + nvcc 존재 하드 체크 추가
#      (CUDA 확장 빌드에 필요, 여긴 print만 하고 넘어가던 이전 00/01과 달리 여기서 exit 1).
#   5. 실패해도 그 시점까지의 pip freeze/환경 상태가 남도록 trap 기반 EXIT 핸들러 추가
#      (이전 버전은 모든 단계가 성공한 뒤에만 pip freeze를 실행해 실패 시 기록이 전혀 안 남았음).
#
# 이 스크립트 자체는 아직 5090/Linux에서 실행해보지 않았다 — 문법 검사(bash -n)만 통과한 상태.
# "실기 검증 필요" 항목은 같은 폴더의 PhysX-3D_수정완료_vs_실기검증필요.md 참고.
set -euo pipefail

if [ ! -f "./setup.sh" ] || [ ! -d "./vox2seq" ]; then
  echo "[중단] 현재 디렉터리가 PhysX-3D 저장소 루트가 아닌 것 같습니다(setup.sh 또는 vox2seq/ 없음)." >&2
  echo "        cd PhysX-3D 후 다시 실행하세요." >&2
  exit 1
fi

if ! command -v nvcc >/dev/null 2>&1; then
  echo "[중단] nvcc를 찾을 수 없습니다 — diffoctreerast/vox2seq 등 CUDA 확장을 빌드할 수 없습니다." >&2
  echo "        CUDA Toolkit 설치 및 PATH 설정 후 다시 실행하세요." >&2
  exit 1
fi

TS=$(date +%Y%m%d_%H%M%S)
LOGDIR="./logs"
mkdir -p "$LOGDIR"

# 실패해도 그 시점까지의 패키지 상태를 남긴다(성공 시에도 마지막에 한 번 더 정상 스냅샷을 남김).
save_env_snapshot() {
  local status="$1"
  pip freeze > "$LOGDIR/pip_freeze_${TS}_${status}.txt" 2>&1 || true
  echo "[$status] 환경 스냅샷 저장: $LOGDIR/pip_freeze_${TS}_${status}.txt"
}
on_exit() {
  local ec=$?
  if [ "$ec" -eq 0 ]; then
    save_env_snapshot "success"
  else
    save_env_snapshot "FAILED_exit${ec}"
  fi
  exit "$ec"
}
trap on_exit EXIT

{
  echo "=== [1/6] setup.sh로 설치 가능한 것들 (xformers, kaolin, vox2seq 제외 — 이유는 파일 상단 주석) ==="
  # setup.sh는 `source`/`.`으로 실행해야 함(내부에서 conda activate, return 등을 씀)
  . ./setup.sh --basic --flash-attn --diffoctreerast --spconv --mipgaussian --nvdiffrast

  echo
  echo "=== [2/6] vox2seq 수동 설치 (공식 setup.sh의 extensions/vox2seq 경로가 저장소에 없어 우회) ==="
  mkdir -p /tmp/extensions
  cp -r ./vox2seq /tmp/extensions/vox2seq
  pip install /tmp/extensions/vox2seq

  echo
  echo "=== [3/6] kaolin 수동 설치 (공식 wheel 인덱스에서 2.7.1+cu128 빌드 존재 확인됨) ==="
  pip install kaolin -f https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.7.1_cu128.html

  echo
  echo "=== [4/6] xformers — 기본적으로 생략 ==="
  echo "이유: 01에서 torch==2.7.1을 고정 설치했는데, xformers 0.0.35(PyPI 최신)는 torch>=2.10을"
  echo "요구한다(PyPI 메타데이터로 직접 확인). 'pip install xformers'를 그냥 돌리면 pip 리졸버가"
  echo "torch를 끌어올려 앞서 설치한 kaolin/CUDA 확장과의 호환성이 깨질 위험이 있다."
  echo "example.py의 실제 기본 attention 백엔드는 flash_attn이라(코드로 직접 확인,"
  echo "trellis/modules/attention/__init__.py BACKEND='flash_attn') xformers 없이도 동작한다."
  echo "정말 xformers를 쓰고 싶다면 이 스크립트를 자동 실행하지 말고, torch==2.7.1과 실제로"
  echo "호환되는 xformers 버전을 사람이 직접 찾아 버전을 못박아 설치할 것 — '--no-deps'만으로"
  echo "설치하는 것은 torch 업그레이드만 막을 뿐 ABI/wheel 호환성 자체를 보장하지 않는다."
  echo "(FORCE_XFORMERS=1 bash 02_install_deps.sh 로 재실행하면 아래 블록에서 강제 설치를 시도함 —"
  echo " 단, 이 경로는 실기 검증 전이므로 기본값은 항상 생략이다.)"
  if [ "${FORCE_XFORMERS:-0}" = "1" ]; then
    echo "[FORCE_XFORMERS=1 감지] 사용자가 명시적으로 강제 설치를 요청함 — 시도한다(위험 감수)."
    pip install --no-deps xformers || echo "[실패] xformers 강제 설치 실패 — flash_attn 백엔드로 계속 진행 가능."
  else
    echo "[SKIP] xformers 설치를 건너뜀(기본 동작)."
  fi

  echo
  echo "=== [5/6] clip(OpenAI CLIP) 설치 — setup.sh 어디에도 없어서 빠져 있던 것, 수동 추가 ==="
  echo "주의: 'pip install clip'은 이름이 겹치는 다른 패키지이므로 절대 쓰지 말 것"
  pip install git+https://github.com/openai/CLIP.git

  echo
  echo "=== [6/6] ipdb (example_render_gt_foreval.py가 import하는데 setup.sh에 없음, 평가 단계 대비 미리 설치) ==="
  pip install ipdb

  echo
  echo "=== 설치 검증 — 실제 기본 백엔드(flash_attn)를 포함해 전부 import 되는지 확인 ==="
  python -c "
import torch, torchvision
print('torch', torch.__version__, 'torchvision', torchvision.__version__)
import clip
print('clip: OK')
import kaolin
print('kaolin:', kaolin.__version__)
try:
    import xformers
    print('xformers:', xformers.__version__)
except ImportError as e:
    print('xformers: 설치 안 됨 -', e, '(기본 백엔드가 flash_attn이라 없어도 됨, 의도된 상태)')
import flash_attn
print('flash_attn:', flash_attn.__version__, '(실제 기본 attention backend)')
import vox2seq
print('vox2seq: OK')
import diffoctreerast
print('diffoctreerast: OK')
from diff_gaussian_rasterization import GaussianRasterizer, GaussianRasterizationSettings
print('diff_gaussian_rasterization(mip-splatting): OK')
import spconv
print('spconv: OK')
import nvdiffrast
print('nvdiffrast: OK')
"

  echo
  echo "=== pip check (의존성 충돌 탐지) ==="
  pip check || echo "[경고] pip check가 충돌을 보고했습니다 — 위 출력을 확인하세요."

} 2>&1 | tee "$LOGDIR/02_install_deps_${TS}.log"

echo "완료. 다음: 03_download_checkpoints.sh 실행"
