# Isaac Sim URDF importer 최소 headless 진단

## 결론

기존 host smoke에서 `isaacsim.asset.importer.urdf-3.11.10`, `omni.physics`, `omni.physx` startup은 확인됐지만, public importer API 성공은 확인되지 않았다. URDF 변환·USD 변환·GT 물리 구동은 실행하지 않았다.

기존 `SimulationApp`의 기본 경험이 `isaacsim.exp.base.python.kit`에서 `isaacsim.exp.base.kit`을 의존하고, 그 base 경험이 `omni.isaac.ml_archive`를 직접 시작한다는 것을 설치 파일에서 확인했다. 이 확장은 URDF importer의 runtime `[dependencies]`에는 없다. 따라서 importer만 검사할 때 base 경험을 쓰는 것은 불필요한 legacy ML Torch load를 포함한다.

## 실제 오류와 분류

### GPU 1 host smoke

로그: `/home/minsujo/Desktop/SH/PHYSx/logs/isaac-sim-install-smoke/20261002T080000Z-single-gpu/`

설정은 `active_gpu=1`, `multi_gpu=false`, `/renderer/multiGpu/enabled=false`, `CUDA_VISIBLE_DEVICES` unset이었다. GPU 1 활성화 및 다음 extension startup 후 첫 importer-related library diagnostic은 다음과 같다.

```text
isaacsim.asset.importer.urdf-3.11.10 startup
omni.physics ... startup
omni.physx ... startup
Import error: .../extsDeprecated/omni.isaac.ml_archive/pip_prebundle/torch/lib/libc10_cuda.so:
undefined symbol: cudaGetDriverEntryPointByVersion, version libcudart.so.12
```

이것은 `omni.isaac.ml_archive` bundled `libc10_cuda.so`의 runtime ABI import 오류다. Python traceback은 없었다. 이 사실만으로 URDF importer API가 직접 실패했다고 단정하지 않는다. 기존 runner가 marker 없이 launcher exit code 0을 성공으로 볼 수 있었던 문제를 새 runner에서 고쳤다.

### Codex 분리 smoke

로그: `/home/minsujo/Desktop/SH/PHYSx/logs/isaac-sim-importer-diagnosis/20261002T090000Z-minimal-importer-diagnosis/`

기본 app, empty stage, importer enable/API 모두 Python marker 전에 `NVML_ERROR_DRIVER_NOT_LOADED`, `activeGpu index 1 is higher than available GPUs`를 먼저 기록했다. 이 세 결과는 `BLOCKED_BY_CODEX_GPU_ACCESS`다. 일반 Linux terminal에서 확인된 driver 595.84와 RTX 5090 두 장, GPU 1의 `physxgen` CUDA 사용 가능을 반박하지 않는다. Codex의 device 접근 제한을 host driver 장애로 기록하지 않는다.

## 공식 권장 방식과 최소 experience

NVIDIA의 [URDF importer extension 문서](https://docs.isaacsim.omniverse.nvidia.com/6.1.0/py/source/extensions/isaacsim.asset.importer.urdf/docs/index.html)는 다음 둘 중 하나로 extension을 활성화하도록 한다.

- application command line: `--enable isaacsim.asset.importer.urdf`
- experience `.kit`의 `[dependencies]`: `"isaacsim.asset.importer.urdf" = {}`

새 `isaac_minimal_usd_physx.kit`와 `isaac_minimal_urdf_importer.kit`은 후자의 공식 방식만 사용한다. 설치 폴더 파일을 편집하지 않으며, 두 experience의 명시 dependency에는 `omni.isaac.ml_archive`, ML, ROS가 없다. importer의 설치본 runtime dependency인 `isaacsim.asset.importer.utils`, `isaacsim.asset.transformer.rules`, `isaacsim.core.experimental.utils`, `isaacsim.pip.newton`, `omni.usdex.libs`는 extension manager가 해결한다. `verify_minimal_experience.py`는 이 명시 dependency와 single-GPU renderer setting을 CPU에서 검사한다.

## GPU 1 및 IOMMU 정책

- `IOMMU is enabled` 경고는 기록만 한다. BIOS·커널·driver·CUDA는 변경하지 않는다.
- host smoke는 물리 GPU 1만 사용한다: `active_gpu=1`, `physics_gpu=1`, `multi_gpu=false`, `/renderer/multiGpu/enabled=false`.
- P2P와 다중 GPU는 활성화·시험하지 않는다.
- `CUDA_VISIBLE_DEVICES`는 사용하지 않는다. Isaac의 CUDA/Omniverse device-order 경고를 피하고 physical GPU index를 고정한다. 설정 근거는 NVIDIA [Setup Tips](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_faq.html) 및 [SimulationApp API](https://docs.isaacsim.omniverse.nvidia.com/latest/py/source/extensions/isaacsim.simulation_app/docs/api.html)다.

## marker-gated host 재현 명령

```bash
/home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/04_한계및후속작업/2026-10-02_IsaacSim_Importer_API_진단/run_host_single_gpu_importer_smoke.sh
```

새 runner는 아래를 별도 process로 검사하고 raw stdout/stderr 및 process/result exit code를 각각 남긴다.

1. minimal Kit Isaac app 실행
2. minimal Kit empty USD stage 생성
3. importer experience에서 `isaacsim.asset.importer.urdf` enable 확인
4. `URDFImporterConfig()` 생성까지의 public API 최소 호출

각 marker가 없으면 process exit code가 0이어도 result exit code `70`으로 실패한다. URDF 경로를 주거나 `import_urdf()`를 호출하지 않는다. 로그는 `/home/minsujo/Desktop/SH/PHYSx/logs/isaac-sim-importer-diagnosis/`, 임시 script는 `/home/minsujo/Desktop/SH/PHYSx/staging/isaac-sim-importer-diagnosis-*`에만 생성된다.
