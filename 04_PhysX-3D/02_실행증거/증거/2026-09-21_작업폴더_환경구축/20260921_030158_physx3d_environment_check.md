# PhysX-3D 읽기 전용 환경 확인

- 날짜/시간대: 2026-09-21, Asia/Seoul (+09:00)
- 최초 조회 시각: 2026-09-21T03:01:58+09:00
- 후속 디스크/경로 조회 시각: 2026-09-21T03:03:39+09:00
- 작업 루트: `/home/minsujo/Desktop/SH/PHYSx`
- 지정 환경: `/home/minsujo/Desktop/SH/PHYSx/envs/physxgen`
- 범위: GPU/드라이버 정보, 현재 nvcc 경로·버전, 지정 환경 패키지, 디스크, CUDA 12.8 패키지 기록과 실제 파일 대조.

## 결론

현재 조회한 파일시스템에서 CUDA 12.8의 실제 toolkit 디렉터리와 컴파일러·헤더·라이브러리는 없다. dpkg의 installed 기록 및 일부 문서·pkg-config 파일은 남아 있다. 현재 nvcc는 실제 존재하는 CUDA 12.2이다. 따라서 패키지 목록만 보고 CUDA 12.8을 사용할 수 있다고 판단할 수 없고, PATH나 링크 변경만으로 해결할 수 있는 상태도 아니다.

`envs/physxgen`은 Python 3.10.21과 기본 패키지로 구성된 환경이다. 해당 환경의 Python 배포판 메타데이터와 디렉터리에는 PyTorch, torchvision, NumPy, FlashAttention, Kaolin 등 모델 의존성이 없다. GPU 계산이나 CUDA 컴파일을 실행하지 않았으므로 실제 연산 호환성은 확인하지 않았다.

설치·삭제·설정 변경·apt update·autoremove·컴파일·GPU 실험·기존 프로젝트 스크립트 실행은 하지 않았다. GPU 조회는 nvidia-smi의 정보 조회만 수행했다. 이번 쓰기 작업은 이 보고서와 별도 패키지 목록 JSON을 `logs`에 저장한 것뿐이다. 인증정보, 전체 환경변수, 셸 이력, 기존 터미널 로그는 읽거나 기록하지 않았다. 네트워크 요청 및 권한 상승도 없었다.

## GPU와 드라이버 — 직접 조회

실행 명령:

```bash
nvidia-smi --query-gpu=index,name,driver_version,memory.total,memory.used,memory.free,utilization.gpu --format=csv,noheader
nvidia-smi --query-compute-apps=gpu_uuid,used_gpu_memory --format=csv,noheader
```

조회 결과:

```text
0, NVIDIA GeForce RTX 5090, 595.84, 32607 MiB, 401 MiB, 31708 MiB, 13 %
1, NVIDIA GeForce RTX 5090, 595.84, 32607 MiB, 64 MiB, 32048 MiB, 5 %
```

compute-apps 조회 결과는 빈 출력이었다. GPU 사용률은 위 시점의 스냅샷으로, 유휴 또는 향후 독점 사용을 보장하지 않는다. 조회 셸 묶음 exit code는 0이었다. GPU 연산을 시작한 명령은 없다.

## OS와 호스트 컴파일러 — 직접 조회

- `/etc/os-release`: Ubuntu 24.04.3 LTS.
- `uname -r`: `6.8.0-138-generic`.
- `gcc --version`, `g++ --version`: Ubuntu `13.3.0-6ubuntu2~24.04.1`, 버전 `13.3.0`.
- Python 자체의 빌드 문자열은 GCC 14.3.0이다. 이는 현재 호스트 GCC/G++ 13.3.0과 별개다.

## 현재 nvcc — 직접 조회

```bash
command -v nvcc
type -a nvcc
nvcc --version
ls -l /usr/local/cuda /usr/local/cuda/bin/nvcc
readlink -f /usr/local/cuda/bin/nvcc
```

- 명령 해석 경로: `/usr/local/cuda/bin/nvcc`.
- 실제 경로: `/usr/local/cuda-12.2/bin/nvcc`.
- `/usr/local/cuda`는 `/usr/local/cuda-12.2/`를 가리키는 직접 심볼릭 링크다.
- nvcc 실제 파일 크기: `21,281,160` bytes. 실행 가능한 일반 파일이다.
- 버전 출력:

```text
nvcc: NVIDIA (R) Cuda compiler driver
Copyright (c) 2005-2023 NVIDIA Corporation
Built on Tue_Aug_15_22:02:13_PDT_2023
Cuda compilation tools, release 12.2, V12.2.140
Build cuda_12.2.r12.2/compiler.33191640_0
```

이 결과는 이번 명령 실행 셸에서의 경로 해석이다. 셸 초기화 파일이나 PATH/CUDA_HOME 설정은 변경하지 않았다. `--version` 조회만 했으며 소스를 컴파일하지 않았다.

## CUDA 12.8 — 패키지 기록과 실제 파일 대조

조회 명령:

```bash
dpkg-query -W -f='${binary:Package}\t${Status}\t${Version}\n' '*-12-8'
dpkg -L cuda-nvcc-12-8 cuda-nvvm-12-8 cuda-crt-12-8 cuda-cudart-12-8 cuda-cudart-dev-12-8 cuda-toolkit-12-8 cuda-compiler-12-8
```

두 조회 exit code는 0이다. 주요 패키지 기록은 다음과 같다.

| 패키지 | dpkg 상태 | 버전 |
|---|---|---|
| cuda-toolkit-12-8 | install ok installed | 12.8.1-1 |
| cuda-compiler-12-8 | install ok installed | 12.8.1-1 |
| cuda-nvcc-12-8 | install ok installed | 12.8.93-1 |
| cuda-nvvm-12-8 | install ok installed | 12.8.93-1 |
| cuda-crt-12-8 | install ok installed | 12.8.93-1 |
| cuda-cudart-12-8 | install ok installed | 12.8.90-1 |
| cuda-cudart-dev-12-8 | install ok installed | 12.8.90-1 |

`*-12-8`에서 `install ok installed` 상태인 56개 패키지를 대상으로 각각 `dpkg -L`을 실행했다. 56개 조회 모두 exit code 0이다. 그 목록 중 `/usr/local/cuda-12.8` 아래 경로를 중복 제거하면 파일·디렉터리·링크를 합쳐 4,082개이며, `os.path.lexists()`로 확인한 실제 존재 경로는 **0개**다. 이 숫자는 일반 파일 4,082개라는 뜻이 아니다.

경로 대조는 `/usr/bin/python3 -B -`의 표준 라이브러리 스크립트로 수행했고 exit code 0이었다. 핵심 로직:

```python
query = subprocess.run(
    ['dpkg-query', '-W',
     '-f=${binary:Package}\t${Status}\t${Version}\n', '*-12-8'],
    text=True, capture_output=True)
rows = [line.split('\t') for line in query.stdout.splitlines()
        if '\tinstall ok installed\t' in line]
all_paths = set()
for package, status, version in rows:
    listing = subprocess.run(
        ['dpkg', '-L', package], text=True, capture_output=True)
    paths = [p for p in listing.stdout.splitlines()
             if p.startswith('/usr/local/cuda-12.8')]
    all_paths.update(paths)
print(len(all_paths), sum(os.path.lexists(p) for p in all_paths))
# 4082 0
```

### 실제로 없는 대표 경로

```text
/usr/local/cuda-12.8
/usr/local/cuda-12.8/bin/nvcc
/usr/local/cuda-12.8/bin/ptxas
/usr/local/cuda-12.8/bin/nvlink
/usr/local/cuda-12.8/bin/cudafe++
/usr/local/cuda-12.8/nvvm/bin/cicc
/usr/local/cuda-12.8/nvvm/libdevice/libdevice.10.bc
/usr/local/cuda-12.8/targets/x86_64-linux/include/cuda.h
/usr/local/cuda-12.8/targets/x86_64-linux/include/cuda_runtime.h
/usr/local/cuda-12.8/targets/x86_64-linux/include/crt/host_config.h
/usr/local/cuda-12.8/targets/x86_64-linux/lib/libcudart.so.12.8.90
/usr/local/cuda-12.8/version.json
```

`/usr/bin/nvcc`, `/opt/cuda`, `/opt/cuda-12.8`, `/opt/nvidia/cuda-12.8`도 없었다. 지정 환경의 `bin/nvcc`, `targets`, `include/cuda.h`, `lib/libcudart.so`, `lib/python3.10/site-packages/nvidia/cuda_nvcc/bin/nvcc`도 없었다. 없는 파일을 포함한 `ls`는 exit code 2와 `No such file or directory`를 반환했다.

12.8 nvcc 자체가 없어 절대경로 `--version`은 실행하지 않았다. 전체 디스크를 검색하거나 다른 사용자 저장소를 조사한 것은 아니므로 임의의 다른 경로에 있는 별도 설치본까지 없다고 단정하지 않는다.

### 남아 있는 대표 파일

| 경로 | 크기(bytes) |
|---|---:|
| `/usr/share/doc/cuda-nvcc-12-8/copyright` | 63021 |
| `/usr/lib/pkgconfig/cudart-12.8.pc` | 239 |
| `/var/lib/dpkg/info/cuda-nvcc-12-8.list` | 1028 |
| `/var/lib/dpkg/info/cuda-nvcc-12-8.md5sums` | 1150 |

따라서 CUDA 12.8 관련 파일이 전혀 없다는 뜻이 아니다. 실행에 필요한 toolkit 트리와 컴파일러가 없는 반면 패키지 관리 기록·문서·일부 설정용 파일은 남아 있다. 누락 원인이나 시점, 실제 삭제 여부/행위자는 이번 조회로 확인하지 않았다.

### CUDA 링크와 alternatives 조회

| 링크 | 최종 대상 | 대상 존재 |
|---|---|---|
| `/usr/local/cuda` | `/usr/local/cuda-12.2` | 있음 |
| `/usr/local/cuda-12` → `/etc/alternatives/cuda-12` | `/usr/local/cuda-12.8` | 없음 |
| `/etc/alternatives/cuda` | `/usr/local/cuda-13.0` | 없음 |
| `/etc/alternatives/cuda-13` | `/usr/local/cuda-13.0` | 없음 |

`readlink -e /usr/local/cuda-12`는 exit code 1, 빈 출력이었다. CUDA 13.0도 위 경로에서 실제 디렉터리가 없지만 이번 주된 조사 대상은 12.8이다.

초기 조사에서 읽기 전용 `update-alternatives --query cuda`, `update-alternatives --query cuda-12`를 실행했으며 다음 경고를 받았다.

```text
update-alternatives: warning: alternative /usr/local/cuda-12.8 (part of link group cuda) doesn't exist; removing from list of alternatives
update-alternatives: warning: alternative /usr/local/cuda-13.0 (part of link group cuda) doesn't exist; removing from list of alternatives
update-alternatives: warning: alternative /usr/local/cuda-12.8 (part of link group cuda-12) doesn't exist; removing from list of alternatives
```

설정 변경 옵션은 사용하지 않았다. 두 조회를 포함한 셸 묶음 exit code는 0이며, 마지막 명령 `--query cuda-12`는 exit code 0이다. `--query cuda`의 개별 exit code는 따로 수집하지 않았다. 경고 문구 자체를 설정 파일이 실제 수정되었다는 증거로 해석하지 않는다. 이후 alternatives 명령은 추가 실행하지 않았다.

## 지정 Python 환경 패키지 — 메타데이터 직접 조회

- 실행 파일: `/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python`.
- 실제 파일: `/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python3.10`.
- Python: `3.10.21 (main, Aug 27 2026, 14:42:07) [GCC 14.3.0]`.
- `sys.prefix`: `/home/minsujo/Desktop/SH/PHYSx/envs/physxgen`.
- 조사 경로: `envs/physxgen/lib/python3.10/site-packages`.

| Python 배포판 | 버전 |
|---|---|
| packaging | 26.3 |
| pip | 26.2.1 |
| setuptools | 83.0.0 |
| wheel | 0.47.0 |

총 4개 Python 배포판 메타데이터가 발견됐다. site-packages 디렉터리 목록으로도 이를 확인했다. conda-meta에는 Python·기본 런타임 라이브러리를 포함한 32개 패키지 기록이 있다. 두 숫자는 서로 다른 목록이므로 합산하지 않는다.

지정 Python을 `-I -B -S`로 실행해 표준 라이브러리 `importlib.metadata.distributions(path=[지정 site-packages])`와 `conda-meta/*.json`을 읽었다. 제3자 라이브러리를 import하거나 site 초기화 코드를 실행하지 않았고 bytecode 파일 생성을 비활성화했다. 프로브 exit code는 0이다. conda JSON은 name/version/build/subdir만 추출했으며 인증정보가 포함될 수 있는 URL/channel/config 전체를 기록하지 않았다.

전체 패키지 목록: [20260921_030158_physxgen_package_inventory.json](20260921_030158_physxgen_package_inventory.json).

## 디스크 — 직접 조회

실행 명령:

```bash
df -hT /home/minsujo/Desktop/SH/PHYSx /home/minsujo/Desktop/SH/PHYSx/envs/physxgen /tmp /usr/local
df -i /home/minsujo/Desktop/SH/PHYSx /tmp /usr/local
df -B1 --output=source,fstype,size,used,avail,pcent,target /home/minsujo/Desktop/SH/PHYSx /tmp /usr/local
```

작업 루트, 지정 환경, `/tmp`, `/usr/local`은 모두 `/dev/nvme0n1p2`의 ext4 공간을 사용한다. 경로별 용량을 합산할 수 없다.

- `df -hT`: 총 `916G`, 사용 `375G`, 가용 `495G`, 사용률 `44%`.
- 후속 byte 단위 조회: 총 `982,820,896,768`, 사용 `402,163,195,904`, 가용 `530,657,615,872` bytes (약 494.2 GiB 가용).
- inode: 총 `61,022,208`, 사용 `2,035,479`, 가용 `58,986,729`, 사용률 `4%`.
- 용량은 조회 시점 값이며 모델·캐시·환경·빌드·출력이 같은 파티션을 사용하면 모두 이 여유 공간을 소비한다.

## 다음에 필요한 작업 — 이번에는 수행하지 않음

1. **CUDA 12.8 파일 복구 방안 정리:** 패키지 DB와 실제 경로가 불일치하는 원인을 확인하고, 실제 toolkit 파일을 복구/재설치할 방법과 영향을 검토한다. 필요하면 다른 설치 위치나 마운트 차이도 확인한다. 현재는 링크나 PATH만 바꿔서는 없는 nvcc를 사용할 수 없다. 기존 12.2나 드라이버 삭제, autoremove를 선행 작업으로 삼지 않는다.
2. **지정 환경의 설치안 작성:** 현재 기본 Python 환경을 기준으로 준비 문서의 PyTorch/cu128 등 후보와 컴파일러·CUDA 확장 패키지 버전 조합을 구체화한다. 패키지는 아직 설치하지 않았다.
3. **설치 및 실행을 진행하는 후속 단계:** 변경 범위가 확정된 후 실제 파일 복구와 패키지 설치를 수행하고, 그 다음 별도 단계에서 작은 컴파일/연산 검증과 공식 예제로 넘어간다. 이번 환경 조회만으로 CUDA 12.8이나 모델의 실행 가능성을 검증했다고 보고하지 않는다.
