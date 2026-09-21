# 2026-09-21 — 로컬 설치 자료 보완과 다음 검사 순서

검토 기준 게시본: `b9fb49be22e1d12ed31e09341b47daff58ca7fa7`. 작업 루트: `/home/minsujo/Desktop/SH/PHYSx`(이하 `PHYSx`). **현재 CUDA와 기본 Python 패키지를 재설치하지 않는다.** 이번 변경은 자료 보완·읽기 전용 검사·다음 명령 준비다. 설치·빌드·모델 다운로드·GPU 실행을 수행한 결과가 아니다.

## 먼저 읽을 자료와 현재 상태

| 구분 | 자료 | 해석 |
| --- | --- | --- |
| 팀원 비교·채택 근거 | [통합실행계획](../../PhysX-3D_팀원비교_통합실행계획.md) | 연구 단계와 선택 근거; 예전 설치 스크립트를 일괄 실행하지 않는다. |
| 최신 Linux 로컬 설치 계획 원본 | [installation-plan.md](local-records/logs/install-plan-20260921/installation-plan.md) | 격리·CLIP 보완을 반영한 설치 **이전** 문서. “미설치”와 설치 명령은 작성 당시 상태다. |
| 실제 CUDA 설치 결과 | [설치 일지](../../실험일지/2026-09-21_작업폴더격리_환경구축_실험일지.md), [result.json](local-records/logs/cuda-toolkit-install-20260921/result.json) | Toolkit 12.8.1, NVCC 12.8.93, 118개 구성 대조·지정 실제 파일 검사 완료. 컴파일/GPU 실행 미검증. |
| 실제 Python 설치 결과 | [설치 일지](../../실험일지/2026-09-21_기본Python패키지_설치.md), [result.json](local-records/logs/python-foundation-install-20260921/result.json) | Python 3.10.21 환경에 고정 wheel 169개, 기존 pip 포함 170개 배포판 대조 및 pip check 완료. |
| 이번 자료 검증 | [자료 manifest](materials-manifest.json), [verify_materials.py](verify_materials.py) | 파일 크기·SHA256 및 foundation 필수 입력 검증. 실제 설치/import/GPU 검증을 대신하지 않는다. |
| 다음 GPU 검사 준비 | [GPU 안내](gpu/README.md) | 기존 설치용 격리 실행기와 분리. 이번에는 계획 출력·정적/모의 검사만 수행한다. |

PyTorch **2.7.1+cu128**, torchvision **0.22.1+cu128**을 유지한다. CLIP, utils3d 및 CUDA source 확장, spconv/cumm 후보는 아직 설치하지 않았다. 현재 상태의 근거는 위 설치 완료 로그이며, 이번 자료 보완 중 패키지 import나 GPU 재검사를 수행한 것은 아니다.

## Windows/Linux에서 안전하게 자료만 검토하기

저장소 루트에서 다음 하나만 실행하면 된다. 표준 라이브러리만 사용하며 자료를 읽고 결과 JSON을 출력한다. 설치 실행기를 import하거나 실행하지 않고 네트워크·GPU에 접근하지 않는다.

```powershell
# Windows: 이미 있는 Python 3 사용. 이 검토를 위해 새 패키지를 설치하지 않는다.
python -I -B -S "04_PhysX-3D/재현자료/2026-09-21_자료보완/verify_materials.py"
```

```bash
# Linux: repro-records 루트에서 실행
/usr/bin/python3 -I -B -S '04_PhysX-3D/재현자료/2026-09-21_자료보완/verify_materials.py'
```

`pass: true`, exit0이면 manifest에 있는 파일의 무결성과 foundation 입력 연결을 확인한 것이다. 실패하면 해당 경로를 확인하며 설치 명령으로 해결하지 않는다. `.gitattributes`는 이 자료 폴더의 자동 줄바꿈 변환을 막아 Windows checkout에서도 원본 SHA256을 유지한다. Windows의 실제 실행 검증은 아직 하지 않았다.

## 누락 보완과 원본 경로

`local-records/` 아래는 Linux 원본의 `logs/...` 구조를 그대로 보존한 **검토용 사본**이다. 57개 원본 파일의 크기·SHA256·원래 상대 경로는 manifest의 `source_relative_to_PHYSx`에 기록한다. 원본은 수정하지 않는다. 최신 계획서의 SHA256은 `206484ebfe56b1396833ba0c8ff7f53ed672a3003e07f5d823cdc2258fafbb96`이다.

`install_foundation.py`가 읽는 고정 파일은 다음 10개다. `PLAN=local-records/logs/install-plan-20260921`, `PYRUN=local-records/logs/python-foundation-install-20260921`이다.

| 위치 | 파일 | 역할 / 이전 게시본 |
| --- | --- | --- |
| PYRUN | `install_foundation.py`, `pip_without_site.py` | 실제 설치 실행기와 site 자동 실행 우회; 기존 증거에도 있음 |
| PYRUN | `before.json` | 설치 전 4개 배포판 상태와 7개 입력 SHA256; **게시 누락 보완** |
| PLAN | `workspace_isolation.py`, `isolation_probe.py` | GPU를 숨기는 설치 격리와 검사; 기존 증거에도 있음 |
| PLAN | `python-foundation.lock.txt`, `python-resolved.constraints.txt` | 실제 설치 대상 169개 wheel과 버전 제약; 기존 증거에도 있음 |
| PLAN | `python-sparse-candidate.lock.txt` | **게시 누락 보완**; 이번 foundation 설치 대상이 아닌 해시 확인 입력 |
| PLAN | `pip-dry-run-initial-report.json`, `pip-utils3d-dry-run-report.json` | **게시 누락 보완**; 의존성·artifact metadata 조회 근거 |

두 pip 보고서는 wheel/model 본체가 없는 텍스트 metadata다. `pip-dry-run-report.json`은 initial 보고서와 같은 바이트지만 역사적 manifest의 두 이름을 모두 보존했다. 최신 계획의 상대 링크에 필요한 검토 자료, CLIP 원문 3개와 patch, CUDA 설치 전 상태/미리보기 입력도 함께 보완했다.

설치 실행기는 `PHYSx/logs/...` 절대 경로를 읽는다. **이 사본을 Windows에서 실행하거나, 사본 폴더에서 실행하면 독립적으로 설치되는 구조가 아니다.** 감사용 사본을 기존 `logs` 위에 복사하지 않는다. 두 설치 실행기는 현재 환경에서 실패해도 기존 `status.json`·`failure.log`를 덮어쓸 수 있어 “실행해서 확인”하지 않는다. `derive_resolved_plan.py`도 lock을 다시 쓰므로 실행하지 않는다.

## 실제로 수행했던 순서와 앞으로의 순서

| 순서 | 단계 | 이번 시점 상태 / 실행 조건 |
| --- | --- | --- |
| 1 | 환경·기존 시스템 조사 → 버전/경로 고정 → 격리 미리보기 | 완료한 과거 기록을 읽는다. |
| 2 | CUDA 새 미리보기 → 118개 구성/artifact 대조 → explicit Toolkit 설치 → NVCC/헤더/라이브러리 확인 | 완료. `toolchains/cuda-12.8.1`을 재설치하지 않는다. |
| 3 | foundation baseline/169개 lock 확인 → wheel 다운로드·SHA256·의존성 검사 → offline preview → 설치 → 버전/pip check | 완료. `envs/physxgen`을 재설치하지 않는다. |
| 4 | 이번 누락 자료·해시·실행 순서 보완, GPU 전용 검사 준비 | 이번 작업 범위. |
| 5 | 한 GPU UUID를 선택하고 기본 PyTorch import/작은 GPU 연산과 사용량 기록 | **다음 승인 대상**. GPU 안내의 실행 명령은 아직 실행하지 않았다. |
| 6 | 누락 source 패키지·CUDA 확장의 고정 버전/빌드 명령 검토 → 개별 빌드·import/연산 확인 | 미실행. 5번 결과를 보고 별도 승인 후 진행. |
| 7 | 고정 소스에 CLIP cache patch 확인·적용 → 모델 저장 경로/용량/revision 확인 → 다운로드·해시 | 미실행. 모델 호출 전에 완료해야 한다. |
| 8 | 공식 예제 → 통합 계획의 추론/학습/정량 검증 | 미실행. 위 전제 충족 후 별도 승인. |

실제 설치 명령과 exit/stdout/stderr는 기존 [CUDA 증거](../../증거/2026-09-21_작업폴더_환경구축/README.md), [foundation 증거](../../증거/2026-09-21_기본Python패키지/README.md)에 연결되어 있다. 계획서의 초기 direct pip 예시를 실제 169개 offline wheel 설치 명령과 혼동하지 않는다.

CUDA 실행기에는 사본 11개 외에도 당시 Conda 캐시의 `info/repodata_record.json` 입력 21개가 필요했고, 새 미리보기의 FETCH 구성에 따라 추가 입력이 달라진다. 캐시 본체는 Git에 넣지 않았다. [외부 입력 목록](external-inputs.json)은 로컬 metadata의 위치·크기·실측 SHA256만 기록한다. [118개 승인 artifact](local-records/logs/cuda-toolkit-install-20260921/approved-artifacts.json)와 [explicit 목록](local-records/logs/cuda-toolkit-install-20260921/cuda-toolkit.explicit.txt)을 함께 읽는다. 새 컴퓨터의 재설치에는 새 baseline·캐시/입력 준비·미리보기 대조가 필요하며 이 묶음만으로 독립 설치가 검증된 것은 아니다.

## CLIP 다운로드 경로 보완

[clip-cache-path.review.patch](local-records/logs/install-plan-20260921/clip-cache-path.review.patch)는 PhysX 소스 `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`의 `example.py`, `dataset_toolkits/merge_property.py` 두 `clip.load` 호출에 다음 인자를 명시한다. CLIP 기준 소스는 `d05afc436d78f1c48dc0dbf8e5980a9d471f35f6`이며 [source-pins.json](local-records/logs/install-plan-20260921/source-pins.json)에 함께 있다.

```python
download_root=os.environ["PHYSX_CLIP_DOWNLOAD_ROOT"]
```

경로는 `/home/minsujo/Desktop/SH/PHYSx/cache/clip`로 고정한다. **`PHYSX_CLIP_DOWNLOAD_ROOT`는 CLIP이 자동으로 읽는 변수가 아니다.** 환경 변수만 지정하면 부족하므로 위 patch와 실행 환경 설정이 모두 필요하다. patch는 현재 미적용이며, [기존 검토 결과](local-records/logs/install-plan-20260921/clip-cache-review.json)는 원문·AST·메모리 내 patch 대조 근거다. 실제 소스 checkout에 대한 `git apply --check`·적용·모델 저장 검증은 후속 작업으로 남는다. patch SHA256은 `8fcc8f32d510b201e3985276aa59da359bb43e76d5dd59db1f9fc0b4a9af224b`이다.

승인 후 소스 commit과 변경 상태를 먼저 확인하고 `git apply --check <patch 경로>`를 수행한다. 성공해도 patch 적용이나 모델 다운로드가 끝난 것은 아니다. 적용 후 두 호출·경로를 다시 확인한다. `clip.load(..., device="cpu")`도 모델을 내려받을 수 있으므로 단순 경로 확인용으로 호출하지 않는다. ViT-L-14.pt의 URL상 기대 SHA256 `b8cca3fd41ae0c99ba7e8951adf17d267cdb84cd88be6f7c2e0eca1737a03836`은 다운로드 파일을 실측한 값이 아니다.

## 검증 범위와 공개 제외

`materials-manifest.json`이 이번 묶음의 기준이다. `isolation-review-sha256.json`의 역사적 34개 항목도 원본과 일치한다. 더 오래된 `artifact-sha256.json`의 계획/작업로그 값은 보완 전 해시여서 최신 파일과 일부 다르며, 최신 검증 기준으로 사용하지 않는다. 원본 증거의 시점 차이를 숨기기 위해 옛 manifest를 고치지 않는다.

환경·캐시·모델·데이터·대형 결과·인증정보는 공개하지 않는다. 자료 검증/정적 검사/계획 출력의 실행별 stdout·stderr·exit은 `PHYSx/logs/repro-materials-20260921/`에 기록하고 필요한 소형 증거만 [검증 기록](validation/)에 선별한다. GPU 실행 및 사용량 측정은 이번 단계에서 미실행이다. 다음 단계에서도 실제 실행 결과와 미검증 항목을 분리하고 [기록 규칙](../../실험일지/기록_및_공유_운영규칙.md)을 따른다.
