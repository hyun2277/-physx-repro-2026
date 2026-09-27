# 작업 폴더 전용 설치 계획 작성 기록

> 이 파일의 본문은 최초 계획 작성 당시 기록이다. 이후 설치 격리/CLIP 재검토 및 제한적인 경로 검사 결과는 [isolation-review-log.md](isolation-review-log.md)에 추가 기록했다. 최초 보고서/해시는 보존했으며 실제 설치·빌드·GPU 실행은 여전히 수행하지 않았다.

- 날짜: 2026-09-21, Asia/Seoul.
- 시작 조회 시각: 03:09:55+09:00.
- 환경 보존 재확인 시각: 03:53:32+09:00 (최종 확인 JSON은 별도 첨부).
- 요청 범위: 계획 작성, 공개 자료·패키지 metadata 확인, 필요시 설치 미리보기. 실제 설치/삭제/시스템 설정 변경/컴파일/GPU 실험 없음.
- 결과 문서: [installation-plan.md](installation-plan.md).

## 수행과 결과

1. 기존 통합 계획과 검토용 설치 스크립트를 읽었다. 기존 스크립트는 실행하지 않았다. 공식 PhysX SHA `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`의 setup.sh를 읽기용 `.txt`로 저장했다. SHA256은 `5f4dec73de2c673342ddbde3f0fd6529d979408f71e08cd25fa7931afe69698c`이다.
2. 기존 Conda는23.3.1, `/usr/bin/gcc-13` 및 `/usr/bin/g++-13`은13.3.0이었다. 버전 조회만 수행했다. 드라이버나 GPU를 새로 실행 시험하지 않았다.
3. `CONDARC=/dev/null`을 사용한 첫 Conda dry-run은 이 구형 Conda의 config 로더에서 `KeyError:8192`로 실패했다(exit1). 시스템 설정을 고치는 대신 이 작업 전용 `preview.condarc`를 logs에 만들고 해당 명령에만 지정했다. 실패 보고서의 전체 환경변수는 작업 로그에 복사하지 않았다.
4. 샌드박스 내 네트워크 조회는 DNS 오류로 실패했다. 명령별 네트워크 실행 승인 후 재시도했다. 보호 설정이나 TLS 검증을 변경하지 않았다.
5. 기본 current_repodata를 사용한 Conda dry-run은 응답 처리 중 JSONDecodeError로 실패했다(exit1). `--repodata-fn repodata.json`으로 지정한 재시도는 **exit0, success=true, dry_run=true**로 완료됐다. 공식 label의 linux-64/noarch repodata는 정상 응답을 확인했다. 실패 원인을 noarch404로 단정하지 않는다.
6. 성공한 Conda 명령의 핵심은 다음과 같다. 각 호출에는 PHYSx 아래 CONDA_PKGS_DIRS, CONDA_ENVS_PATH, XDG_CACHE_HOME, TMPDIR와 작업 전용 CONDARC를 지정했다.

   ```bash
   /home/minsujo/anaconda3/condabin/conda create --dry-run --json \
     --repodata-fn repodata.json \
     --prefix /home/minsujo/Desktop/SH/PHYSx/toolchains/cuda-12.8.1 \
     --override-channels --strict-channel-priority \
     -c https://conda.anaconda.org/nvidia/label/cuda-12.8.1 \
     -c https://repo.anaconda.com/pkgs/main cuda-toolkit=12.8.1
   ```

   결과는 [conda-cuda128-dry-run.json](conda-cuda128-dry-run.json)에 있다. LINK118개, UNLINK0개, FETCH97개/2,100,106,977 bytes는 **설치 계획값**이다. Toolkit prefix는 생성되지 않았다. exact version/build 목록118개를 생성하고 LINK와 일치함을 별도 읽기 전용 검토로 확인했다.
7. CUDA12.8.1의 일반 GCC 지원표는6.x–14.x지만, 선택한 Conda nvcc-dev12.8.93 빌드는 gcc_impl>=6,<14를 요구한다. 이번 solver는 GCC/GXX11.2와 runtime15.2를 골랐다. 실제 빌드 계획은 기존 host GCC/G++13.3을 절대경로로 고정한다. Python 빌드 GCC, runtime, host compiler를 혼동하지 않는다.
8. PyPI JSON과 공식 source/tag/commit/wheel index를 조회했다. package archive를 설치하거나 source setup.py를 실행하지 않았다. 메타데이터 조회 스크립트는 URL/버전/의존성/파일 해시 필드만 저장한다. 인증 설정, 토큰, HTTP Set-Cookie를 로그에 복사하지 않았다.
9. 지정 Python으로 `pip install --dry-run --only-binary=:all: --report ...`를 수행했다. 최초 샌드박스 DNS 실패 반복은 중단(exit130)하고 승인된 네트워크 호출로 재시도했다. **첫 완전한 미리보기는167개 패키지, exit0**이며 [pip-dry-run-initial-report.json](pip-dry-run-initial-report.json)에 보존했다. `pip-dry-run-report.json`은 같은 최초 성공 결과가 남아 있다.
10. utils3d 의존성 추가 후 전체 재미리보기는 일부 NVIDIA wheel을 다시 다운로드하여 불필요한 반복을 중단했다(exit1, pip 메시지는 Operation cancelled by user이지만 작업자가 중단한 것). 이후 기존 해결 버전의 constraints 아래 추가 패키지만 미리보기했다. 마지막 좁은 미리보기는 moderngl5.12.0, plyfile1.1.2, glcontext3.0.0, psutil7.0.0 및 기존 NumPy1.26.4의5개 항목을 제시했고 exit0이었다. [pip-utils3d-dry-run-report.json](pip-utils3d-dry-run-report.json).
11. 두 성공 보고서를 합치면171개 고유 패키지다. 기본 wheel169개와 미검증 sparse 후보2개(spconv/cumm)를 분리하여 URL+SHA256 목록을 만들었다. 활성 기본 dependency metadata의 누락/버전 충돌은0건이다. 이 결과는 optional extras 전수 검증이나 설치·빌드·런타임 검증이 아니다.
12. 보고서에 SHA256이 없던 Jinja2/MarkupSafe wheel은 각각 공개 URL에서 PHYSx/cache/pip으로 받은 뒤 SHA256을 직접 계산했다. 초기 lock 생성 과정에서 누락 hash와 공식 redirect 호스트(pypi.nvidia.com/download-r2.pytorch.org) 검사로 중단됐고 이를 근거에 맞게 반영한 뒤 오프라인 생성이 성공했다. 최종 파일은 [python-metadata-validation.json](python-metadata-validation.json)과 [supplemental-wheel-hashes.json](supplemental-wheel-hashes.json)을 참조한다.
13. pip dry-run은 일부 NVIDIA wheel의 metadata 제공 방식 때문에 **wheel 전체를 임시 폴더로 다운로드**했다. 이 작업은 설치가 아니며 지정 환경은 그대로였다. 캐시/임시 파일은 PHYSx/cache 및 PHYSx/tmp로 지정했다. 중간 관찰값은 cache/conda474M, cache/pip32M, cache/xdg4K, tmp/install-plan91M이었다. 이는 당시 디스크 사용량이며 총 네트워크 전송량이 아니다. 사용자의 삭제/정리 요청이 없어 별도 cache clean/autoremove를 수행하지 않았다.

## 독립 읽기 전용 검토로 보완한 항목

- 현재 Conda는 실제 create 시 `~/.conda/environments.txt`를 touch/append한다. cache/prefix 변수로 막을 수 없다. HOME을 변경하지 않고 PHYSx만 writable인 일회성 bwrap 격리 안에서 후속 설치하도록 계획을 보완했다. `/usr/bin/bwrap` 존재만 확인했으며 격리 기동/전체 설치는 아직 미검증이다. 이번 dry-run이 그 등록 파일을 수정했다는 뜻은 아니다.
- 공식 첫 예제와 merge_property.py의 OpenAI CLIP `clip.load`는 download_root가 없다. 실행 전 작업용 소스에 PHYSx/cache/clip을 명시해야 한다. 이번에는 공식 소스/패치를 수정하지 않았다.
- spconv/cumm에 존재하지 않는 cache 환경변수를 만들어 해결됐다고 주장하지 않았다. JIT 출력이 package root 아래라는 소스 근거와 별도 CUDA_CACHE_PATH/TMPDIR를 계획에 기록했다.
- spconv-cu1262.3.8/cumm-cu1260.7.11의 메타데이터 일치와 RTX5090 실제 연산 지원은 다르다. 후자는 미검증이다. 별도 후보 목록으로 분리했다.

## 보존 확인과 남은 작업

03:53:32 조회에서 지정 Python 배포판4개(packaging26.3/pip26.2.1/setuptools83.0.0/wheel0.47.0)는 이전 환경 점검 JSON과 같았고 conda-meta는32개였다. Toolkit prefix는 없었다. 기록 저장소는 main, 작업 트리 clean이었다.

다음 단계는 문서에 제시한 설치 격리가 외부 쓰기를 차단하는지 먼저 검증한 뒤, 사용자가 실제 설치를 진행하기로 할 때 Toolkit/기본 wheel/소스 확장을 단계별로 설치하는 것이다. 현재 시스템 CUDA 복구, 드라이버 변경, 다른 환경 수정은 계획에 포함하지 않는다. GPU 연산/예제/모델 본체 다운로드는 아직 수행하지 않았다.
