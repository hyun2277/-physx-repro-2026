# Isaac Sim 6.1.0 분리 설치와 importer smoke 기록

## 범위와 결론

Isaac Sim standalone 6.1.0을 `/home/minsujo/Desktop/SH/PHYSx/tools/isaac-sim/`에 분리 설치했다. PhysXGen의 `envs/physxgen`, 공식 PhysX-3D source, checkpoint, 기존 25표본 산출물은 수정·이동·삭제하지 않았다. `post_install.sh`도 실행하지 않았다.

공식 compatibility checker는 Ubuntu 24.04.3, NVIDIA driver 595.84, RTX 5090 두 장을 확인하고 `PASSED`를 기록했다. 다만 처음 checker는 `CUDA_VISIBLE_DEVICES=1`을 사용해 Isaac이 경고한 구성이다. 이후 smoke는 `CUDA_VISIBLE_DEVICES` 없이 물리 GPU 1만 `active_gpu=1`로 선택하고 `multi_gpu=false`, `/renderer/multiGpu/enabled=false`를 사용했다. P2P와 다중 GPU는 활성화하거나 시험하지 않았다.

`isaacsim.asset.importer.urdf` 3.11.10은 설치 bundle에 존재하고 startup 기록도 있다. 그러나 importer Python API까지 도달했다는 성공 판정은 내리지 않았다. GPU 1 single-GPU smoke에서 선택적 legacy extension `omni.isaac.ml_archive`가 `/usr/local/cuda/lib64/libcudart.so.12`를 해석한 뒤 `libc10_cuda.so`의 `cudaGetDriverEntryPointByVersion` ABI symbol 오류를 냈다. launcher exit code 0만으로 importer API 성공을 판단할 수 없다. 시스템 CUDA·driver·심볼릭 링크는 변경하지 않았다.

이 기록은 설치 및 importer 준비 상태만 다룬다. URDF 생성·USD import·GT 물리 구동·AI generated-output 변환은 실행하지 않았다.

## IOMMU 및 GPU 사용 정책

- Isaac 로그에 `IOMMU is enabled` 경고가 기록됐다.
- BIOS와 커널 설정은 변경하지 않았다.
- 이후 Isaac smoke와 GT 대조군은 물리 GPU 1만 사용한다: `active_gpu=1`, `multi_gpu=false`, `/renderer/multiGpu/enabled=false`.
- P2P와 다중 GPU 실행은 하지 않는다.
- Codex 실행 환경에서 발생한 NVML/GPU 열거 실패는 일반 Linux 호스트의 driver 장애로 해석하지 않는다. 사용자가 일반 Linux terminal에서 GPU 0·1 RTX 5090, driver 595.84 및 GPU 1의 `physxgen` CUDA 사용 가능을 별도로 확인했다.

## 공식 설치 근거

- [NVIDIA Isaac Sim 다운로드](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/download.html): Linux standalone 6.1.0 및 공식 MD5 `b471383a51f259e0af22541f05c34b0e`.
- [Quick Install](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/quick-install.html): Linux standalone 설치와 공간 요구 안내.
- [Requirements](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html): Ubuntu 24.04 및 driver 요구사항.
- [URDF Importer](https://docs.isaacsim.omniverse.nvidia.com/latest/importer_exporter/import_urdf.html): `isaacsim.asset.importer.urdf`의 공식 importer 안내.

정확한 URL·hash·공간·smoke 판정은 [install_manifest.json](install_manifest.json), [smoke_summary.json](smoke_summary.json)에 있다.

## 다음 허용 단계

single-GPU host terminal에서 legacy ML extension의 ABI 문제를 NVIDIA 공식 지원 경로로 분리할 수 있는지 확인한 뒤 importer API smoke를 다시 판정한다. 그 전에는 GT URDF/USD/Isaac 물리 대조군을 시작하지 않는다.
