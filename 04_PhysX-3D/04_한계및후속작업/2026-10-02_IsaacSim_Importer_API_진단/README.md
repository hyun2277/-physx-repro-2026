# Isaac Sim standalone importer API 진단

## 목적과 범위

이 기록은 Isaac Sim 6.1.0의 **기본 app**, **빈 USD stage**, **URDF importer enable/API**를 URDF 변환 없이 분리해 검사한다. GT URDF/USD 변환, GT 물리 구동, generated-output 변환은 실행하지 않았다.

공식 Isaac Sim 6.1.0은 Kit SDK 110.3.0을 사용하며, 설치된 `python.sh`는 Python 3.12.13이다. 설치 bundle에는 `isaacsim.asset.importer.urdf` 3.11.10이 있다. NVIDIA의 [URDF importer 문서](https://docs.isaacsim.omniverse.nvidia.com/6.1.0/py/source/extensions/isaacsim.asset.importer.urdf/docs/index.html)는 standalone에서 `--enable isaacsim.asset.importer.urdf` 또는 experience의 `[dependencies]`를 권장한다. [공식 standalone tutorial](https://docs.isaacsim.omniverse.nvidia.com/latest/importer_exporter/import_urdf.html)은 `./python.sh standalone_examples/api/isaacsim.asset.importer.urdf/urdf_import.py`를 제시하지만, 이 진단은 변환을 호출하지 않는다.

## 기존 importer smoke의 실제 오류 순서

### GPU 1이 열거된 2026-10-02T080000Z smoke

`active_gpu=1`, `multi_gpu=false`, `/renderer/multiGpu/enabled=false`, `CUDA_VISIBLE_DEVICES` unset으로 시작했다. Isaac 로그에서 GPU 1이 active로 표시되고 `isaacsim.asset.importer.urdf-3.11.10` startup도 표시됐다. 그 뒤 최초 importer-related library 오류는 다음과 같다.

```text
Import error: .../extsDeprecated/omni.isaac.ml_archive/pip_prebundle/torch/lib/libc10_cuda.so:
undefined symbol: cudaGetDriverEntryPointByVersion, version libcudart.so.12
```

이는 Python traceback이 아니라 Isaac의 extension import diagnostic이다. `omni.isaac.ml_archive`의 bundled `libc10_cuda.so`가 해당 CUDA runtime symbol을 찾지 못했다는 **library ABI 오류 관찰**까지는 확정된다. 이 오류가 URDF importer public API를 직접 차단하는지, host의 정상 GPU 환경에서 importer import 자체가 통과하는지는 아직 확정하지 않았다. launcher exit code 0과 extension startup만으로 API 성공을 주장하지 않는다.

### 현재 Codex 2026-10-02T090000Z 분리 진단

`01_basic_app`, `02_usd_stage`, `03_urdf_enable_api`는 모두 실제 Python marker 전에 다음 runtime device diagnostic이 먼저 발생했다.

```text
Could not initialize NVML: NVML_ERROR_DRIVER_NOT_LOADED
The chosen activeGpu index 1 is higher than the available GPUs.
No device could be created.
```

따라서 이 세 결과는 각각 `BLOCKED_BY_CODEX_GPU_ACCESS`이며, USD stage와 importer enable/API는 **도달하지 못했다**. 사용자가 일반 Linux terminal에서 확인한 RTX 5090 두 장, driver 595.84, GPU 1의 `physxgen` CUDA 성공과 모순되지 않는다. Codex 실행 환경의 NVML/GPU 접근 제한을 호스트 driver 장애로 기록하지 않는다.

## 단일 GPU 및 IOMMU 정책

- 설치/host checker 로그의 `IOMMU is enabled` 경고를 기록한다. BIOS·커널 설정은 변경하지 않는다.
- 이후 host smoke와 GT 대조군은 물리 GPU 1만 사용한다: `active_gpu=1`, `physics_gpu=1`, `multi_gpu=false`, `/renderer/multiGpu/enabled=false`.
- `CUDA_VISIBLE_DEVICES`는 Isaac이 CUDA/Omniverse enumeration 차이를 경고했으므로 사용하지 않는다.
- P2P와 다중 GPU는 활성화하거나 시험하지 않는다.
- GPU selection 근거는 NVIDIA [Setup Tips](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_faq.html)와 [SimulationApp API](https://docs.isaacsim.omniverse.nvidia.com/latest/py/source/extensions/isaacsim.simulation_app/docs/api.html)다.

## 결과 구분

| 검사 | 현재 Codex 결과 | host에서 확정된 결과 |
|---|---|---|
| Isaac 기본 실행 | GPU access 전에 차단 | compatibility checker `PASSED`; standalone Python marker는 재확인 필요 |
| 빈 USD stage 생성 | 도달하지 못함 | 미확정 |
| importer extension enable | 도달하지 못함 | bundle/startup 확인, enable API는 미확정 |
| importer public API import | 도달하지 못함 | legacy ML ABI diagnostic 이후 미확정 |

## 재현 명령

일반 Linux host terminal에서 다음 하나만 실행한다. URDF 파일·GT·AI 산출물을 읽거나 쓰지 않는다.

```bash
/home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/04_한계및후속작업/2026-10-02_IsaacSim_Importer_API_진단/run_host_single_gpu_importer_smoke.sh
```

이 runner는 stdout marker가 없으면 launcher exit code가 0이어도 실패로 처리하고, 첫 실패 이후 뒤 단계를 실행하지 않는다. 로그와 staging은 `/home/minsujo/Desktop/SH/PHYSx/logs/isaac-sim-importer-diagnosis/` 및 `/home/minsujo/Desktop/SH/PHYSx/staging/isaac-sim-importer-diagnosis-*` 아래에만 만든다.
