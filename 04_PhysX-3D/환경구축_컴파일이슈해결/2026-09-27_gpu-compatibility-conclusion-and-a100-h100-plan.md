# 5090 호환성 결론과 A100/H100 실행 계획

## 일반 터미널 확인 결과

사용자가 일반 Linux 터미널에서 확인한 공식 근접 환경은 다음과 같다.

- `torch 2.4.0+cu118`이 RTX 5090 장치를 인식했다.
- 해당 PyTorch cu118 빌드가 지원하는 CUDA capability 상한은 `sm_90`이었다.
- RTX 5090은 `sm_120`이므로 이 환경은 장치를 열거할 수 있어도 5090용 CUDA 커널 실행 지원 범위 밖이다.
- 따라서 table 예제와 29354 inference는 실행하지 않았다.

현재 두 환경의 결론:

| 환경 | 핵심 조합 | RTX 5090 결론 | 기존 관찰 |
|---|---|---|---|
| `envs/physxgen` | torch 2.7.1+cu128, spconv-cu126 2.3.8, cumm-cu126 0.7.11 | sm_120 실행은 가능했으나 native/implicit_gemm 모두 cumm/spconv int32 제한으로 실패 | N=2,168,704, C=512에서 int32 range 초과 |
| `envs/physxgen-cu118-official` | torch 2.4.0+cu118, torchvision 0.19.0+cu118, spconv-cu118 2.3.8, cumm-cu118 0.7.11 | 5090은 인식하지만 PyTorch 지원 상한 sm_90으로 실행 부적합 | 일반 터미널 capability 확인으로 차단; 예제 미실행 |

이번 확인은 GPU 호환성 판정이며 논문 성능이나 예제 성공 판정이 아니다.

## A100/H100 별도 GPU 계획

실행 대상은 공식 cu118 지원 범위에 있는 별도 호스트 또는 예약 GPU로 한정한다.

1. 동일한 `physxgen-cu118-official` manifest를 새 호스트의 PHYSx 내부 환경에 재현한다. Python 3.10.21, torch 2.4.0+cu118, torchvision 0.19.0+cu118, spconv-cu118 2.3.8, cumm-cu118 0.7.11을 고정하고 `pip check`와 package/wheel hash를 기록한다.
2. 실행 전 A100 `sm_80` 또는 H100 `sm_90`인지, `nvidia-smi`와 `torch.cuda.get_device_capability()`가 일치하는지 확인한다. 다른 GPU나 5090이면 중단한다.
3. 입력은 기존 29354 conditioning PNG를 그대로 사용한다: `/home/minsujo/Desktop/SH/PHYSx/staging/render-cond-29354-portable-20260925T185825Z/datasets/PhysXNet/renders_cond/29354_/000.png`.
4. checkpoint는 기존 manifest를 그대로 검증한다: `04_PhysX-3D/자료확보/evidence/29354-inference-checkpoint-manifest.txt`. 입력 PNG, transforms와 checkpoint hash가 일치할 때만 실행한다.
5. 별도 runner는 source HEAD `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`, 허용된 pyc-only tracked 변경, GPU 1 보호, 새 timestamp 출력 폴더, stdout/stderr/GPU 사용량/종료 코드 기록을 포함한다. 공식 `example.py`의 native 설정은 유지한다.
6. table 예제를 먼저 한 번 검증하고, 그 결과와 GPU capability가 모두 통과할 때만 29354 native inference를 한 번 실행한다. 실패 시 같은 명령을 반복하지 않는다.

이 문서는 계획만 기록한다. 새 GPU 예약, 데이터·checkpoint 다운로드, 환경 재설치, table 실행, 29354 추론은 수행하지 않았다.
