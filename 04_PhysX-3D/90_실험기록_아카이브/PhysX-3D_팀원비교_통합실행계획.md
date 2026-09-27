# PhysX-3D 팀원 자료 비교 및 통합 실행 계획

검증일: 2026-09-21. 판정: 양쪽 준비본을 그대로 합쳐 실행하는 것은 권하지 않는다. 우선 추론 환경을 확정하고, 정량 평가 경로를 별도로 완성해야 한다. GPU 실험은 아직 수행하지 않았다. 이 문서는 실행 순서와 통합 결정서이며, 미구현 평가기를 완성했다고 주장하는 문서가 아니다.

## 사용자 제공 실제 서버 환경 — 비교 후 추가 확인

사용자가 2026-09-21 전달한 터미널 출력 기준이며 Codex가 원격 서버에 직접 접속한 것은 아니다.

| 항목 | 확인값 | 실행 판단 |
|---|---|---|
| OS | Ubuntu 24.04.3 LTS, kernel 6.8, x86_64 | Linux 기준 계획 사용 |
| GPU | RTX5090 2장, 각각 32607MiB | 먼저 1장으로 검증. 메모리 64GB가 자동 합쳐지는 것은 아님 |
| driver | 595.84, nvidia-smi CUDA 표시 13.2 | 표시값은 driver 지원 상한; nvcc와 구분 |
| 현재 nvcc | 12.2.140 | sm_120 직접 타깃 빌드용으로 부적합. 다른 toolkit 설치 여부부터 확인 |
| RAM | 총125Gi, available118Gi | 현재 여유 확인, 미래 점유 보장 아님 |
| 저장소 | / 파티션 916G, 가용496G | 기본 모델/소규모 평가 준비부터 사용. XL 전체 저장에 부족 |
| 프로세스 | 조회 시 GPU util0%, 데스크톱 프로세스 사용 | 실행 직전 점유 재확인 |

NVIDIA [CUDA12.8 release notes](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-toolkit-release-notes/)에서 SM_120 compiler 지원 추가를 확인했다. [driver/toolkit 설명](https://docs.nvidia.com/datacenter/tesla/drivers/cuda-toolkit-driver-and-architecture-matrix.html)도 nvidia-smi CUDA 표시를 지원 상한으로 설명한다. 현재 torch cu128 후보를 유지한다면 toolkit12.8을 일치시키는 것이 우선이다. 기존12.2 삭제나 시스템 driver 교체부터 하지 않는다. 다른 버전이 이미 설치됐다면 새 환경에서 CUDA_HOME/PATH를 선택할 수 있다.

다음 조회만 수행한 뒤 설치 방법을 확정한다:

```bash
command -v nvcc
readlink -f "$(command -v nvcc)"
ls -ld /usr/local/cuda* /opt/cuda* 2>/dev/null
gcc --version | head -n 1
g++ --version | head -n 1
conda env list
```

맨 앞 npm/nvm 경고는 Node 환경 설정 문제로, 이번 Python/CUDA 설치의 직접적인 오류 증거는 아니다. 이 작업을 위해 npm 설정 변경 명령을 실행할 필요는 없다. Linux 저장소에는 Windows D:를 그대로 사용하지 않고 실제 / 아래 작업 경로 및 여유 공간을 기록한다.

## 검토 대상과 증거

- 팀원 ZIP의 Markdown 8개. 실행 가능한 설치 스크립트는 포함되어 있지 않다. 최신 실행안은 `06_재현_계획_RTX5090.md`, 환경 분석은 `05_랩실_RTX5090_환경_재검토.md`. 03/04는 이전 개인 PC 계획으로 구분했다.
- 우리 `PhysX-3D_설치스크립트/00~05`, 계획 v2, 검증 문서들, 재생성한 패치 3개 및 패치 적용 검사 결과.
- 공식 로컬 소스 `D:\physX_dev\repos\PhysX-3D`, commit `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`. 확인 당시 clean.
- 논문 [v4 본문·부록](https://arxiv.org/html/2507.12465v4), [공식 저장소](https://github.com/ziangcao0312/PhysX-3D), 두 HF 모델 공개 메타데이터.
- `PhysX-3D_통합검증_증거.json`에 ZIP 각 파일과 우리 스크립트 SHA256, 소스 버전, CPU 진단 결과를 기록했다. `PhysX-3D_통합검증_진단.py`로 재검사 가능하다.
- ZIP의 과거 사용자 결정·명령·외부 메모리 참조는 검토 자료다. 이번 사용자의 대용량 다운로드나 시스템 변경 승인으로 해석하지 않았다.

## 공통점·차이점·통합 결정

| 항목 | 우리 최신 준비본 | 팀원 최신 계획 | 최종 결정 |
|---|---|---|---|
| 목표 | 5090에서 예제와 새 이미지 실행 | 동일 | 공통 출발점으로 채택. 논문 전체 재현과 구분 |
| 코드 | 같은 공식 commit을 검사했지만 clone 명령은 main | 같은 commit을 문서에 기록하고 실행 후 확인 | 실제 checkout을 고정 SHA로 강제 |
| 환경 | Linux 가정, Python 3.10, torch 2.7.1/cu128 고정 | OS 미확인, torch 버전 미지정 cu128 설치 | 실제 OS부터 확인. Linux 기준 스택을 후보로 삼되 실기 통과 후 확정 |
| 어텐션 | 기본 FlashAttention, xformers 생략 | SDPA로 바꾸고 둘 다 생략 | 팀원 안은 그대로 채택 불가. dense와 sparse 둘 다 검증 |
| Kaolin | torch 2.7.1/cu128 인덱스 수동 설치, 버전 미고정 | 0.18.0/torch 2.7.0/cu128 인덱스 | torch/Kaolin 정확한 조합 고정. 최신 torch와 구형 wheel 혼합 금지 |
| 누락 의존성 | 루트 vox2seq 수동 설치, OpenAI CLIP/ipdb 추가 | 최신 실행 명령에 이 보완 없음 | 우리 보완 유지. 의존 라이브러리의 source revision도 고정 |
| 가중치 | hf CLI 사용, revision 없음 | SHA 조사 있음, 실제 명령은 구형 CLI/revision 없음 | 우리 CLI + 팀원 SHA를 결합 |
| 용량 | PhysXGen 약 9GB라는 주석 | 두 저장소 약 15.8GB | 우리 주석 정정 필요. 캐시·환경·데이터 압축 해제 공간은 별도 |
| 검증 | import, CUDA availability, 문법·패치 검사 | CUDA 확장의 실제 연산 검사 강조 | 실제 forward 연산 검사 채택. import 성공만으로 통과시키지 않음 |
| 로그 | 실행 스크립트·시각별 출력·일부 실패 기록 | 상세한 실행 전/중/후 기록 원칙 | 원칙과 자동 기록을 합치고 외부 기록 문서 의존 제거 |
| 공식 코드 결함 | 관절/GT 버그와 패치 검토 | 최신 실행 계획에 패치 통합 없음 | 원본/수정본을 분리하여 동일 입력 비교 |
| 평가 | 아직 예제·이미지 실행까지만 연결 | GT 생성 명령을 평가 단계로 제시, 우선순위 낮음 | 정량 재현 목표에서는 평가 필수. 양쪽에 없는 채점·집계 경로 구현 |
| 데이터 | 상세 용량 조사 부족 | 기본판/XL 구분 및 용량 조사 상세 | 기본판부터. XL은 핵심 표 재현의 선행조건으로 두지 않음 |

좋고 나쁜 계획을 통째로 고르는 문제가 아니다. 팀원의 데이터·하드웨어 조사와 우리 설치 보완·코드 결함 검토를 통합하되, 양쪽의 미검증 가정을 제거해야 한다.

## 실행 전 해결할 발견 사항

### 1. 팀원 SDPA 우회는 전체 모델에 적용되지 않음 — 실행 차단 가능

팀원 06 문서 78~88, 120~127행은 FlashAttention/xformers를 설치하지 않고 `ATTN_BACKEND=sdpa`를 설정한다.
공식 `trellis/modules/attention/__init__.py`는 SDPA를 지원하지만 `trellis/modules/sparse/__init__.py`는 xformers/flash_attn만 허용한다. sparse 기본값은 flash_attn이다. sparse/attention의 full/serialized/windowed 코드가 이를 import하고 호출한다.

소스의 환경 설정 부분만 AST로 추출해 CPU에서 실행한 결과:

```text
ATTN_BACKEND=sdpa, SPARSE_ATTN_BACKEND 미설정
dense: sdpa
sparse: flash_attn
```

따라서 두 패키지를 모두 생략할 근거가 되지 않는다. Linux에서 FlashAttention의 실제 사용 함수들을 우선 검증한다. 실패 시 호환 xformers 스택 또는 sparse SDPA 구현 변경을 별도 검증해야 한다. Windows wheel 부재나 backward 관련 이슈만으로 Linux inference 불가능을 확정할 수 없다.

### 2. 버전 고정이 문서에만 있고 명령에 없음

팀원 06의 torch 무버전 설치와 torch 2.7.0용 Kaolin wheel은 정확히 일치한다고 보장할 수 없다. 우리도 Kaolin/FlashAttention/CLIP/렌더러와 HF revision을 고정하지 않았다. `--no-deps`는 바이너리 호환성 해결책이 아니다. FORCE_XFORMERS 경로는 통합 기본 실행에서 제외한다.

후보 기준은 Python3.10 + torch2.7.1 + torchvision0.22.1 + cu128이다. 이는 5090에서 검증 완료한 환경이라는 뜻이 아니다. 선택한 CUDA toolkit, compiler, flash-attn, Kaolin, spconv, 렌더러와 실제 연산이 모두 맞아야 최종 lock을 만든다. `nvidia-smi`의 CUDA 표시는 설치된 nvcc 버전과 다르므로 두 출력을 함께 보존한다.

### 3. 가중치 용량 및 다운로드

2026-09-21 공개 HF API `?blobs=true`를 조회하여 모든 sibling의 size 존재를 확인했다. 모델 본체 다운로드는 수행하지 않았다.

| 저장소 | revision | 전체 파일 bytes |
|---|---|---:|
| Caoza/PhysXGen | 52598097b7092df495ac149e137050ce2d2784fe | 12,502,208,422 |
| microsoft/TRELLIS-image-large | 25e0d31ffbebe4b5a97464dd851910efc3002d96 | 3,299,240,850 |

합계 15,801,449,272 bytes ≈15.8GB, ≈14.72GiB. 우리 03 스크립트의 '약 9GB' 주석은 부정확하다. 팀원의 '15.8GB면 충분'도 전체 디스크 요구량으로 해석하면 부정확하다. DINOv2/CLIP 등 추가 캐시, 환경·빌드·출력·데이터 저장 공간이 별도로 필요하다. 기본판 15.2GB/XL1.77TB는 팀원 보고값이며 이번 검사에서 데이터 전체 크기를 독립 재산정하지 않았다.

환경 확정 후 사용할 다운로드 형태:

```bash
hf download microsoft/TRELLIS-image-large --revision 25e0d31ffbebe4b5a97464dd851910efc3002d96 --local-dir pretrain/trellis
hf download Caoza/PhysXGen --revision 52598097b7092df495ac149e137050ce2d2784fe --local-dir pretrain
```

### 4. 새 발견: split 중복과 GT 생성 범위

공식 README는 val_test_list.npy의 앞 1,000개가 validation, 뒤 1,000개가 test라고 설명한다. 실제 npy를 pickle 없이 읽어 확인했다:

| 검사 | 값 |
|---|---:|
| 전체 항목 / 고유 ID | 2,000 / 1,878 |
| validation 고유 ID | 973 |
| test 고유 ID | 972 |
| 두 집합의 공통 ID | 67 |

GT 스크립트 87행은 전체 목록을 읽고 자르지 않는다. 저장 폴더도 sample ID만 사용하므로 반복 항목의 결과가 덮어써질 수 있다. 이는 공개 파일에서 확인한 사실이지 논문 실험에서 데이터 누수가 있었다는 증명은 아니다. 같은 물체의 다른 평가 인스턴스인지, 단순 중복인지 추가 메타데이터 확인이 필요하다.

최종 runner는 공식 test의 순서·중복을 원형 보존하고 `split_index + object_id`로 실행 키를 만든다. ID별 GT 캐시와 항목별 예측·집계 기록을 구분한다. 임의로 중복을 제거해 '공식 1K 재현'이라고 하지 않는다. 1,000개 항목 기준과 고유 ID 기준을 필요 시 별도 보고하고, 논문 비교 프로토콜이 불명확하면 그 상태를 명시한다.

### 5. 패치 적용 성공과 과학적 타당성은 별개

패치 3개는 재생성 후 개별 및 6가지 순서 적용·Python 문법 검사를 통과한 기록이 있다. 이번 비교에서도 증거 JSON을 확인했다. 다만 관절 patch01은 부모 그룹의 정수 인덱싱(207행)과 빈 그룹 처리를 해결하지 않는다. patch03의 mesh-to-part 매핑은 실제 데이터 대조 전까지 잠정이다. patch02도 질문 선택·seed·GT와 예측의 일치까지 자동 보장하지 않는다.

원본 baseline은 오류를 포함한 공개 구현의 동작 확인용으로 보존한다. 수정 결과는 별도 라벨과 patch hash를 붙인다. 오류 있는 원본 결과를 유효한 관절 정량 지표로 포장하거나, 수정본을 원본과 동일하다고 부르면 안 된다.

### 6. 우리 스크립트에도 남은 보완

- 01: main clone 이후 고정 checkout, 환경 경로 고정, 실제 CUDA 연산 확인 필요.
- 02: nvcc 존재만이 아니라 버전 확인. 활성 환경 확인, 설치 전후 torch 버전 유지 검사, pip check 충돌 시 중단. 재실행 시 /tmp/extensions clone/copy 충돌 방지. 설치 실패 단계와 exit code 보존.
- 03: 위 revision 고정, 용량 주석 정정, 다운로드 파일 manifest/hash 저장.
- 04/05: 실행 ID 충돌 방지, 코드 diff·입력 hash·seed·질문·설정·exit code 보존. 콘솔 관절명 유무만으로 성공/고정을 판정하지 않음.
- 모든 단계: 캐시·환경·빌드 임시 파일까지 큰 저장소로 지정. 현재 PC는 D: 사용. Linux 서버는 실제 mount를 확인하고 선택하며 D:라는 경로를 추정하지 않음.

## 한 컴퓨터에서 실행할 최종 순서

현재 00~05를 무조건 연속 실행하는 명령은 확정하지 않는다. OS/디스크 확인과 아래 미구현 절차를 반영한 뒤 단계별로 실행한다.

1. **환경 조회**: OS/WSL 여부, GPU·VRAM·드라이버·현재 점유, nvcc, RAM, 저장 mount/공간을 기록. 기존 시스템을 변경하지 않고 시작.
2. **통합 실행본 고정**: 같은 공식 SHA, 독립 conda prefix, 캐시/출력 root 지정. 원본과 패치 실험 소스를 분리. 00/01을 이 조건에 맞게 갱신.
3. **설치와 연산 검사**: 02의 누락 보완을 유지하고 라이브러리별 버전/commit을 고정. torch CUDA 행렬 연산, 모델이 사용하는 flash-attn dense/varlen 함수, sparse conv, vox2seq, renderer, mesh 경로의 실제 forward를 검증. NaN/Inf와 CPU 기준 가능한 연산을 확인. 실패 시 해당 단계 로그를 남기고 추론으로 진행하지 않음.
4. **고정 가중치 다운로드**: 03에 revision·manifest 적용. DINOv2/CLIP 등 추가 네트워크·캐시도 추적. 실제 다운로드/해시 완료 후 진행.
5. **공식 예제**: 04를 통해 table/chair, 고정 seed 실행. 산출물 존재뿐 아니라 열리는지·유한 값인지·예외 없이 끝났는지 검사. VRAM 피크·소요 시간·stdout/stderr 보존. 이 단계는 '추론 성공' 판정.
6. **GT/패치 소규모 검증**: 기본 PhysXNet과 필요한 PartNet/ShapeNet 연계 자료의 실제 구조 확인. 고정/단일관절/복수관절 물체를 포함한 소규모 subset에서 part-mesh, 부모자식, 축·범위, description 질문 일치를 확인. GT 보정 patch03의 가정을 데이터로 검증. 원본과 수정본 비교 기록.
7. **평가 구현 검증**: batch prediction/원시 물리 출력 저장, GT 렌더, metric scoring, 집계기를 연결. GT를 자신과 비교할 때 거리≈0·PSNR의 동일영상 처리·kinematics 매칭의 기대값을 검사. 작은 변형을 주면 지표가 예상 방향으로 바뀌는지도 검사. 테스트셋으로 임계값을 튜닝하지 않음.
8. **공식 test 평가**: 프로토콜을 고정한 뒤 1K 항목 전수 실행. 중단 후 resume, 항목별 실패 상태와 분모, 중복 정책을 보존. 실패 항목을 조용히 제외하지 않고 전체/유효 항목 수와 실패 사유를 함께 보고.
9. **비교·ablation**: 동일 조건에서 논문의 비교 모델과 ablation을 실행. 공개 체크포인트/설정 유무부터 확인하고 없으면 재학습 필요 범위를 명시. 단일 GPU에서 메모리·시간을 측정한 후 학습 계획 결정.
10. **제조 물체 범용성**: 별도 held-out 이미지와 관절 GT를 준비. joint 존재·종류·부모자식·축·위치·범위·분할을 평가하고 공식 benchmark와 구분. 사용자 이미지 추론 성공만으로 범용성을 확정하지 않음.

## '거의 100%'를 판단하는 완료 기준

논문 전체 재현율을 지금 숫자로 예측할 수 없다. 현재 모델 실행 성공 증거 및 Table2 재현 측정치는 아직 없다. 0/9는 확보된 주요 지표 수이지 준비 노력의 비율이 아니다.

| 범위 | 필요한 산출물 | 현재 상태 |
|---|---|---|
| Table2 PhysXGen 주요 결과 | PSNR/CD/F-score, scale, density/affordance/description 맵, kinematics COV/MMD — 총 9지표의 항목별 결과·집계·논문 차이 | 양쪽 준비본에 완전한 평가 경로 없음 |
| Table2 비교 모델 | 각 모델 동일 입력·평가 조건 결과 | 미구현 |
| Table3 ablation | 구성별 모델·설정·동일 평가 결과 | 미구현, 가중치/재학습 필요 여부 확인 |
| 부록 비교/정성/오류 분석 | Table5 및 해당 비교·실패 사례 | 미구현 |
| 학습 재현 | 데이터 준비·학습 설정·checkpoint·평가 | 단일5090 가능 시간/메모리 미측정 |
| 데이터/XL 생성 | annotation/procedural pipeline의 별도 검증 | 주요 pretrained benchmark와 별도 범위 |

평가 전 카메라·렌더 수·해상도·마스크·정규화·거리 단위·point sampling·F-score threshold·PSNR 집계·관절 pose sampling/ID 정의·description 질문을 문서화해야 한다. 공개 자료로 결정할 수 없는 항목은 '논문과 동일'이라고 쓰지 않고 가정/차이로 기록한다. 필요하면 저자에게 문의할 목록을 작성하되 자동으로 메시지를 보내지 않는다.

## 기록 및 공유

각 실행마다 run_id, 코드 SHA/diff, patch hash, 패키지 lock, CUDA/compiler, 모델 revision/hash, split/index/input hash, seed/question/config, 명령, 시작/종료/exit code, GPU 로그, 원시 결과 위치, 실패 원인·다음 수정점을 한 묶음으로 저장한다. 성공뿐 아니라 실패도 commit 단위로 연결한다. 큰 모델/데이터는 저장소에 넣지 않고 경로·hash·받는 방법을 기록한다.

이번 작업은 비교 보고서와 CPU 진단/증거 파일 작성까지다. 기존 양쪽 계획·설치 스크립트와 공식 clone은 변경하지 않았고, 설치·가중치/데이터 다운로드·GPU 실행·Git push는 수행하지 않았다. 남은 실기 검증 때문에 완벽함이나 논문 수치 일치를 보증하지 않는다.

## 재감사 결론: 채택 결정과 실제 구현을 구분

추가 재검토: 사용자의 '모두 검증됐는지/성공률/어느 쪽을 썼는지' 요청에 대한 2026-09-21 갱신.

**현재 판정은 실행 준비 미완료다.** 계획 채택을 스크립트 구현 완료로 읽으면 안 된다. 논문과 프로젝트 페이지, 공식 README/고정 소스, 최신 로컬 파일을 재대조하고 CPU 진단을 다시 통과시켰다. 이는 전 코드·모든 의존성의 무결점 보증이 아니다.

| 출처 | 사용하기로 한 내용 | 실제 반영 수준 |
|---|---|---|
| 팀원 01/02 | 기본판/XL 구분, 모델 revision 조사, 용량 산정 | 본 통합 계획에 반영. 모델 용량/revision은 독립 조회. 03 다운로드 스크립트 revision 옵션은 아직 미반영 |
| 팀원 05/06 | 5090 컴파일 위험, 실제 GPU 연산 검사, 실행 전/중/후 기록 | 검사 원칙 채택. 해당 GPU에서의 연산 검사는 아직 미실행 |
| 우리 01/02 | torch 버전 고정, vox2seq 경로 보완, CLIP/ipdb 수동 설치, 기본 xformers 생략 | 기존 스크립트에 존재. 환경 완전 고정·실기 성공은 아님 |
| 우리 03/04/05 | hf CLI, 타임스탬프 출력, GPU/콘솔 로그 | 기존 스크립트에 존재. 완전한 provenance/충돌 방지/실패 집계는 보완 필요 |
| 우리 공식 패치 | 관절/GT 수정, Git 적용 검증 | patch 파일과 검사 기록 존재. 공식 clone에는 미적용, 데이터/GPU 의미 검증 미완료 |
| 이번 독립 대조 | SDPA sparse 미지원, split 중복/GT 전체순회, 실제 서버 nvcc12.2 | 진단·증거·계획 반영. 서버 설정 변경이나 평가 runner 구현은 미실행 |

채택하지 않는 주장: SDPA 환경변수만으로 FlashAttention/xformers 둘 다 생략 가능, GT 생성 명령 하나로 정량 평가 완료, 최신 torch와 특정 옛 torch용 Kaolin의 일치 보장, 15.8GB가 전체 실행 디스크 요구량, 패치 적용 성공이 모델 정확성 검증 완료라는 주장.

### 추가로 확인한 학습·평가 조사 공백

1. **평가 코드의 재사용 가능성**: 공식 README는 NAP의 Instantiation distance 구현으로 연결한다. [NAP 평가 안내](https://github.com/JiahuiLei/NAP/blob/main/eval/readme_eval.md)는 point-cloud sampling → ID distance matrix → metric notebook 경로를 설명하며 완전히 독립된 모듈이 아니라고 명시한다. 다음 정량 실험 준비에서 변환 어댑터·pose sampling·정규화·COV/MMD 집계를 조사한다. NAP를 설치만 하면 PhysXGen 출력에 바로 적용된다고 가정하지 않는다. 기존 `trellis/utils/loss_utils.py`에는 PSNR 함수도 있다. 따라서 '평가 함수가 전혀 없음'이나 '평가 전체를 처음부터 구현해야 함'은 부정확하고, **현재 우리 실행본에 검증된 전체 평가 경로가 없음**이 정확하다.
2. **학습 코드 존재**: `train.py`, VAE 및 diffusion config가 실제 존재한다. 우리의 '미구현' 표기는 우리 실행 패키지의 연결 상태를 뜻하며 저자가 학습 코드를 공개하지 않았다는 뜻이 아니다. 두 config는 max_steps=1,000,000, VAE batch_size_per_gpu=4, diffusion=16을 명시한다. 논문 비교에는 실제 checkpoint step/전체 batch/누적/optimizer/EMA/전처리 필터도 확인해야 한다. 이 설정으로 걸릴 시간은 측정하지 않았다.
3. **전처리 준비 부족**: `dataset_toolkits/precess.sh`는 속성 병합, texture retrieval, metadata, render/render_cond, voxelization, feature/latent 추출을 연결한다. 압축 해제만으로 학습 입력이 완성되지 않는다. render 스크립트는 Blender3.0.1 다운로드 및 시스템 패키지 설치 경로를 포함한다. Ubuntu24.04/5090에서 해당 경로의 호환성은 미검증이다. 평가 입력을 생성할 때 이 경로를 사용한다면 정량 평가 전에, 재학습만을 위한 단계라면 재학습 전에 검사한다.
4. **멀티 GPU 기본 동작**: `train.py`는 num_gpus 기본값 -1을 visible GPU 전체 개수로 바꾼다. 2장 서버에서 의도치 않게 둘 다 사용하지 않도록 첫 학습 smoke test는 CUDA_VISIBLE_DEVICES 및 `--num_gpus 1`을 명시한다. 2장 사용 시에도 64GB 단일 GPU처럼 취급하지 않으며 전체 batch/통신/재현 조건을 별도 검증한다.
5. **후속 연구와 원 논문 구분**: 공식 README가 언급한 PhysX-Anything의 VLM 평가를 조사할 수는 있지만, 이를 원 논문의 COV/MMD 대신 사용하고 같은 재현이라고 하면 안 된다. 교수님의 제조 물체 범용성 실험에서 보조 평가 후보로 구분한다.

### 지금 반드시 해결 / 다음 확장 실험에서 조사

| 시점 | 항목 | 완료 증거 |
|---|---|---|
| 첫 GPU 추론 전 | CUDA toolkit 선택, compiler/패키지 호환, dense+sparse attention, 렌더러 실제 연산, 코드/모델 고정, 로그 | 버전 lock + 성공/실패 원본 로그 + 예제 산출물 |
| 첫 정량 평가 전 | GT 매핑·관절 잔여 버그, split 중복, 원시 출력 export, NAP 연결 포함 9지표 프로토콜, 데이터/texture 대응 | 소규모 정답 테스트 + 항목별 manifest + 검증된 채점기 |
| 주요 수치 확보 후 | baseline/ablation 가중치 제공 범위, 필요 재학습, training split 오염 여부, 시간/디스크 실측 | 비교 실험별 동일 조건 결과 및 미재현 사유 |
| 범용성 후속 실험 | 제조 물체·비주방 물체, 가림/배경/촬영각 변화, joint별 정확도, seed 변동 | 미리 정한 표본/GT/성공 기준과 실패 유형표 |
| 별도 확장 | XL 필요한 subset, annotation 검증, VLM 보조 평가 | 원 논문 결과와 분리한 보고서 |

핵심 실행/평가 결함은 다음 연구로 미루면 안 된다. 확장 연구만 후순위로 둔다. 다음 논문을 조사할 때에는 설치법뿐 아니라 **평가 입력→예측→GT→지표→집계의 전 경로**, split/중복, checkpoint/설정 대응, 전처리 의존성, GPU 실제 연산, 기록/재시작 조건까지 사전 조사 항목으로 삼는다.

### 성공률 보고 원칙

- '90% 성공할 것' 같은 확률을 산출할 관측 자료가 없으므로 예측값을 제시하지 않는다.
- 현재 실측 주요 지표는 0/9, GPU 추론 성공 증거는 0건이다. 이는 연구 가치나 준비율 0%라는 뜻이 아니다.
- 첫 목표는 Table2 PhysXGen 9개 지표 **평가 범위 9/9 확보**다. 9개를 계산했다는 사실만으로 논문 수치 일치나 전체 논문100% 재현이 되지는 않는다.
- 논문 대비 절대/상대 차이, 단위, seed 변동, 표본 수/실패 수를 보고한다. 동일 허용오차를 서로 다른 단위의 모든 지표에 일괄 적용하지 않는다. 수치 확인 전에 허용오차와 프로토콜을 정한다.
- 한 컴퓨터에서 통합본을 한 번 돌리는 것은 공동 재현이다. 두 팀원의 독립 환경 교차검증이라고 보고하지 않는다. 상호 검토한 준비 자료와 별도로, 평가기 독립 검산이나 seed 반복을 수행하면 그 검증 범위를 명시한다.
