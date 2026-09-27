# 29806 `000.png`·`006.png` 동일-seed 시점 probe 준비

목적은 GT 4 groups에 대해 `000.png` 조건에서 공식 group 수가 2였던 29806을, 기존 conditioning render의 `006.png`와 **동일 seed**로 비교하는 것이다. 이는 논문 공식 평가나 일반 성능 측정이 아니라 단일 입력 시점의 질적 probe다.

기존 sampling 실행의 `sampling_report.json`과 실제 child `command.json`은 모두 `--seed 1`을 기록한다. `sample_latents_only.py`는 `pipeline.get_cond` 뒤, sparse-structure와 SLAT/physics sampling 직전에 `torch.manual_seed(1)`을 호출한다. 따라서 runner는 새 `000.png`와 `006.png` sampling child 모두에 `--seed 1`을 명시한다. 기존 실행의 sampling 전 generator-state snapshot은 별도로 기록되지 않았으므로, 이 준비는 명시된 seed와 코드·checkpoint·환경을 고정하는 비교이며 bitwise 동일성을 주장하지 않는다.

고정 조건:

- object 29806의 기존 24-view conditioning render 및 `transforms.json`을 hash 검증 후 재사용한다. `000.png` SHA256은 `ecc444…cf6ea`, `006.png` SHA256은 `89f691…7782b`이다.
- 고정 source HEAD와 checkpoint manifest, GPU 1 compute-process 보호, per-run CUDA 12.8.1 overlay, GCC/G++ 12, `SPCONV_ALGO=native`를 다시 확인한다.
- input channel tiling, output channel tiling, memory-bounded GroupNorm의 작은 GPU 동등성 검사를 decoder 전 필수 단계로 둔다.
- 각 frame은 sampling, physics decoder, mesh decoder를 별도 child process로 실행한다. decoder마다 current GPU free memory와 예상 peak를 검사하고, 28,000 MiB monitor limit와 4,607 MiB reserve를 유지한다.
- 각 frame은 input hash·seed·command·environment·GPU 기록·latent/mesh/raw/property-head hash를 남긴다. 같은 `verify_articulated_output.py` 규칙으로 group 수·정점·면적·연결요소를 계산한다.

GT part와 생성 mesh 정점의 직접 대응이 없으므로 parent·direction·position·range 정확도를 산정하거나 주장하지 않는다. 이 실행기는 Git push를 수행하지 않는다.

일반 Linux 터미널 실행 명령:

```bash
/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python -B /home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/01_재현실행/자료확보/run_29806_viewpoint_probe.py
```
