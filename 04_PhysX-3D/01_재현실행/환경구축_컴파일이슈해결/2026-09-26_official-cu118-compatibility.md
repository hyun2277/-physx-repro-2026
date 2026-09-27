# PhysX-3D 공식 CUDA 11.8 근접 환경 검사

- 기준 source: `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`
- 공식 `setup.sh` 분기: Python 3.10, `pytorch==2.4.0`, `torchvision==0.19.0`, `pytorch-cuda=11.8`; CUDA major 11이면 `spconv-cu118`을 설치한다. CUDA 12 분기는 `spconv-cu120`이다.
- 새 환경: `/home/minsujo/Desktop/SH/PHYSx/envs/physxgen-cu118-official`
- 기존 `envs/physxgen`, 시스템 CUDA/드라이버, source, 데이터와 모델은 수정하지 않았다.

## 설치 기록

Conda Python 3.10 환경은 PHYSx 내부에 만들었다. Conda solver가 PyTorch 패키지 해석 중 장시간 완료되지 않아 중단했고, 공식 PyTorch cu118 wheel index로 동일한 버전을 설치했다. `spconv-cu118`과 그 공식 PyPI 의존 `cumm-cu118`을 PyPI에서 설치했다. 설치 명령, stdout/stderr, explicit 목록, freeze, wheel hash는 다음 로그에 있다.

`logs/official-cu118-env/20260926T165812Z/`

확인된 버전:

| package | version |
|---|---|
| Python | 3.10.21 |
| torch | 2.4.0+cu118 |
| torchvision | 0.19.0+cu118 |
| spconv-cu118 | 2.3.8 |
| cumm-cu118 | 0.7.11 |
| torch CUDA runtime | 11.8 |

`pip check`는 `No broken requirements found.`를 반환했다. 캐시와 새 환경은 Git에 추가하지 않았다.

## GPU 사전검사

새 환경에서 `torch`, `torchvision`, `spconv-cu118`, `cumm-cu118` import는 성공했다. 그러나 `nvidia-smi`가 `couldn't communicate with the NVIDIA driver`로 실패했고, 같은 검사에서 `torch.cuda.is_available()`가 `False`/device count `0`이었다. 따라서 RTX 5090의 sm_120 capability 확인과 소형 CUDA `SubMConv3d` 연산은 실행할 수 없었다. 이는 패키지 import 실패가 아니라 현재 실행 세션에서 NVIDIA 드라이버가 보이지 않는 차단이다.

직접 근거:

- `logs/official-cu118-env/20260926T165812Z/gpu-preflight.stdout.log`
- `logs/official-cu118-env/20260926T165812Z/gpu-preflight.stderr.log`
- `logs/official-cu118-env/20260926T165812Z/gpu-preflight.exit_code.txt`

사용자 일반 Linux 터미널에서 드라이버가 정상적으로 보이는지 확인하기 전에는 table 예제나 29354 native inference runner를 준비하거나 실행하지 않는다. 이번 작업에서는 조건 미충족으로 두 runner를 만들지 않았다.
