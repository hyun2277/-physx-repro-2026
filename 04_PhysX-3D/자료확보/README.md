# PhysXNet.zip 확보·압축 내부 점검 준비

이 폴더에는 사용자가 직접 실행할 다운로드와 압축 내부 점검 명령만 둔다. 현재 단계에서는 네트워크 다운로드·압축 해제·annotation 읽기를 실행하지 않았다.

고정 출처는 PhysX-3D 데이터 저장소의 revision `ca1f6d3f5cfb5c39dc183251a3a2999dcb42e093`이다. `PhysXNet.zip`의 공식 metadata 크기는 16,306,354,206 bytes (16.31 GB, 15.19 GiB), 공식 LFS SHA256은 `a4970a3936e8a1fc823d17b64d23b167d73997a13686011bc46f7b98774a7e75`이다. 이 값은 metadata에서 가져온 기대값이지 이 컴퓨터에서 계산한 로컬 hash가 아니다.

현재 저장 공간은 `/home/minsujo/Desktop/SH/PHYSx`가 있는 파일시스템 기준 약 441 GB 여유다. 기존 `PhysXNet*.zip` 및 `.part*` 파일은 확인되지 않았다. `cache`는 약 26 GB, `logs`는 약 838 MB였다. 다운로드 파일과 임시 조각은 `PHYSx/data/physxnet-download/` 아래, 로그는 `PHYSx/logs/physxnet-download-20260921/` 아래에 둔다.

## 사용자가 실행할 다운로드 명령

```bash
/home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/자료확보/download_physxnet_zip.sh
```

스크립트는 고정 revision URL을 사용하고, `.part` 파일에 `curl --continue-at -`로 재개한다. 실행 전 예상 크기와 여유 공간을 확인한다. 다운로드가 끝나면 크기와 SHA256을 검사한 뒤에만 `PhysXNet.zip`으로 원자적으로 이름을 바꾼다. 실패하거나 hash가 맞지 않으면 `.part`와 로그를 보존하고 종료하며, 자동으로 보호 설정을 풀거나 압축을 해제하지 않는다. 이미 완성 파일이 있어도 hash가 맞을 때만 성공으로 기록한다.

전체 ZIP을 보관하는 데 필요한 전송량은 약 16.31 GB다. 압축 해제 공간은 내부 목록을 확인하기 전에는 산정하지 않으며, 이 단계에서는 압축을 풀지 않는다. HF 파일 필터로 ZIP 내부의 JSON/OBJ/PNG만 선택하는 방법은 확인하지 않았다.

## 다운로드 후, 압축 해제 전 점검

```bash
/home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/자료확보/inspect_physxnet_zip.py
```

이 점검기는 `zipfile`의 중앙 목록만 읽고 파일을 추출하지 않는다. 기존 공식 test 목록의 뒤 1,000행과 대응하는 `finaljson/<id>.json`, `partseg/<id>/img/`, `partseg/<id>/objs/` 후보를 보고한다. JSON의 `group_info`/joint 관련 필드를 정적으로 읽어 고정·관절 **후보**를 표시하지만, 공식 분류로 승격하지 않는다. JSON이 없거나 구조가 다르면 상태를 `UNRESOLVED`로 남긴다. 40개 texture 경로 누락 ID도 제외하지 않고 별도 목록으로 기록한다.

검사 결과는 archive 목록 hash, test ID별 member 존재, JSON 구조 요약, 고정/관절 후보, 누락 ID와 실행별 stdout/stderr/종료 코드를 로그에 남긴다. 표본 확정·압축 해제·모델 추론·전체 평가는 이후 단계다.
