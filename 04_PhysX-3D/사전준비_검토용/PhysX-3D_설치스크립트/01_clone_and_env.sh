#!/bin/bash
# PhysX-3D clone + conda 환경 생성 + PyTorch 2.7.1(cu128) 수동 설치.
#
# 왜 setup.sh --new-env를 안 쓰는가: 그 플래그는 PyTorch 2.4.0(CUDA 11.8)을 강제로 까는데,
# 2.4.0은 RTX 5090(sm_120)을 지원하지 않는다(PyTorch 2.7.0부터 sm_120 네이티브 지원 시작 —
# 00_연구준비/하드웨어_요구사양_조사.md에서 이미 조사한 사실, 이번에 PyTorch 공식 cu128 wheel
# 인덱스를 직접 확인해 2.7.0~2.9.1까지 실존함을 재확인함).
#
# git clone에 --recurse-submodules를 안 쓰는 이유: .gitmodules 파일이 저장소에 없음을 직접
# 확인함(404) — 플래그를 써도 해는 없지만 아무 의미가 없어서 생략.
set -euo pipefail

TS=$(date +%Y%m%d_%H%M%S)
LOGDIR="./logs"
mkdir -p "$LOGDIR"

{
  echo "=== git clone ==="
  git clone https://github.com/ziangcao0312/PhysX-3D.git
  cd PhysX-3D
  echo "=== 사용 commit ==="
  git rev-parse HEAD
  git log -1 --format="%H %ci %s"

  echo
  echo "=== conda 환경 생성 (python 3.10 — setup.sh --new-env가 못박은 버전과 동일하게 맞춤) ==="
  conda create -y -n physxgen python=3.10

  echo
  echo "=== conda 환경 activate 후 PyTorch 2.7.1 + CUDA 12.8 수동 설치 ==="
  # conda run을 쓰면 이 스크립트를 source 없이 그냥 실행(bash 01_clone_and_env.sh)해도 동작함
  conda run -n physxgen pip install --index-url https://download.pytorch.org/whl/cu128 \
      torch==2.7.1 torchvision==0.22.1

  echo
  echo "=== 설치 확인: PyTorch가 5090(sm_120)을 실제로 잡는지 (실패 시 여기서 강제 종료) ==="
  # Claude 독립검증 §3 / Codex 지적: 기존엔 이 파이썬 코드가 print만 하고 예외를 던지지
  # 않아서, cuda available: False가 나와도 bash 관점에서는 exit 0으로 "정상 종료"됐다.
  # assert로 바꿔서 실패 시 파이썬이 non-zero exit → set -e가 스크립트 전체를 중단시키게 한다.
  conda run -n physxgen python -c "
import torch
print('torch:', torch.__version__)
print('cuda available:', torch.cuda.is_available())
print('cuda version(torch가 링크된 것):', torch.version.cuda)
assert torch.cuda.is_available(), 'CUDA를 사용할 수 없습니다 — 드라이버/설치를 확인하고 중단합니다.'
print('device name:', torch.cuda.get_device_name(0))
print('device capability:', torch.cuda.get_device_capability(0))
cap = torch.cuda.get_device_capability(0)
assert cap >= (12, 0), f'device capability {cap}가 sm_120 미만입니다 — 5090이 아닌 다른 GPU를 잡았을 수 있습니다.'
"
} 2>&1 | tee "$LOGDIR/01_clone_and_env_${TS}.log"

echo
echo "완료. 다음: cd PhysX-3D && conda activate physxgen 한 뒤 02_install_deps.sh 실행"
