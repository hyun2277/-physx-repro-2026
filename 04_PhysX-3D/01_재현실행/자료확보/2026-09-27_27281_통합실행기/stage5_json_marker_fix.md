# 27281 stage 5 JSON marker fix

대상 실행은 `/home/minsujo/Desktop/SH/PHYSx/logs/physx27281-e2e/20260926T204346Z-1023e34e2663/`이다. stage 1~4는 성공했고 stage 5의 CPU/boundary 및 작은 GPU original/tiled/reference 검사는 child exit code 0으로 끝났다. 보존된 마지막 GPU 검사의 stdout에는 adapter 진입 JSON과 수치 동등성 JSON 두 줄이 있으며 stderr는 비어 있다.

직접 실패한 import probe는 기존 runner가 `subprocess.check_output()`의 반환값을 메모리에서 바로 `json.loads()`에 전달했기 때문에 stdout/stderr 원문이 stage 로그에 저장되지 않았다. 따라서 실패 실행에서 import probe 원문 전체를 사후 복구할 수는 없다. 고정 source와 동일 import의 GPU 없는 진단으로 다음 사실을 확인했다.

- `trellis/modules/sparse/__init__.py:27`은 import 중 stdout에 `[SPARSE] Backend: spconv, Attention: flash_attn`을 출력한다.
- `trellis/modules/sparse/conv/__init__.py:13`은 stdout에 `[SPARSE][CONV] spconv algo: native`를 출력한다.
- 기존 성공 decoder 로그에서도 위 두 줄이 결과 JSON 앞에 실제로 기록돼 있다.
- GPU를 감춘 동일 import 진단은 첫 번째 `[SPARSE]` 줄을 stdout에 기록한 뒤 CUDA 장치 초기화에서 중단됐다. GPU 검사는 수행하지 않았다.

따라서 JSON object 하나가 아닌 안내문과 JSON이 섞인 stdout 전체를 `json.loads()`한 것이 `line 1 column 2` 오류의 확정 원인이다. 원문 미보존은 별도의 logging 결함이다.

수정 후 child는 `PHYSX_RESULT_JSON=<json>`을 정확히 한 줄 출력한다. parent는 이 marker로 시작하는 줄이 정확히 하나인지 검사한 뒤 marker 뒤만 JSON object로 파싱한다. marker 없음/복수, JSON object 아님, `trellis`, `spconv`, `cumm`, `algo` 누락, 필드 타입 불일치를 모두 실패 처리한다. 알고리즘이 `native`가 아니거나 trellis 경로가 고정 source 밖이면 계속 중단한다. import probe의 raw stdout/stderr, command, exit code, GPU usage는 각각 `import_probe.*` 파일로 보존한다. CPU/boundary/GPU 동등성 검사도 서로 다른 prefix 로그를 사용하므로 덮어쓰지 않는다.

CPU mock은 noisy stdout 앞뒤, `[SPARSE]` 안내문, marker JSON, warning stderr를 한 child에서 생성했다. marker JSON만 정확히 파싱되고 stderr 원문이 보존됨을 확인했다. marker 없음/복수, 필수 key 누락, 타입 불일치가 모두 거부됐다.

기존 실행의 stage 1~4는 각 단계의 현재 input fingerprint, `SUCCESS.json`, 모든 output SHA256을 runner의 실제 `marker_valid`로 다시 대조했고 네 단계 모두 `true`였다. 아래 명시적 resume에서는 네 단계를 건너뛰고 stage 5의 작은 GPU 동등성 검사를 다시 수행한다. 기존 실패 파일은 유지하고 새 로그를 `05_native_adapter_equivalence/attempt_02/`에 기록한다. sampling과 decoder는 이 수정·검증 과정에서 실행하지 않았다.
