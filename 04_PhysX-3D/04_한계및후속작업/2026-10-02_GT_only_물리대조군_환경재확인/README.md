# GT-only URDF→USD→Isaac Sim 물리 대조군: 환경 재확인

## 범위와 판정

이 기록은 2026-10-02에 기존 GT 입력의 무결성과 Isaac Sim 실행 사전조건만 다시 읽은 결과다. 새 설치·다운로드·GPU 실행·URDF/USD 생성·Isaac Sim 물리 구동은 하지 않았다. 따라서 **GT-only 대조군 실행은 미시작**이며, 성공 또는 실패한 물리 실험이 아니다.

원격을 `fetch`한 뒤 문서 작성 전 local HEAD, `origin/main`, remote `main`은 모두 `79e78369273e342922aa8f17b79f3a6a4df3aab4`였다. 기존 GT 입력 해시 목록의 19개 파일은 모두 현재 파일과 SHA256이 일치했다. 자세한 기계 판독 결과는 [environment_probe.json](environment_probe.json), 입력 목록은 [기존 GT 입력 해시](../2026-10-02_GT_URDF_USD_IsaacSim_대조군_준비감사/gt_input_hashes.csv)에 있다.

| 사전조건 | 이번 확인 | 판정 |
| --- | --- | --- |
| NVIDIA 사용자 공간 접근 | `nvidia-smi`가 NVIDIA driver와 통신하지 못함 | 차단. 이 세션의 접근 실패만 확인했으며, 드라이버 시스템의 원인은 판정하지 않음 |
| Isaac Sim/Kit | 표준 설치 경로와 실행기(`isaac-sim.sh`, `isaacsim.sh`, `omni`, `kit`)를 찾지 못함 | 차단 |
| Python importer | `physxgen`에서 `omni`, `isaacsim` import 불가; `pxr`만 존재 | 차단 |
| URDF importer | Isaac runtime의 `isaacsim.asset.importer.urdf` extension을 검사할 런타임 자체가 없음 | 차단 |
| 디스크 | PHYSx 작업 루트 여유 386,058,883,072 bytes (약 360 GiB) | 공간만 통과; 실행기·driver 부재를 해소하지 않음 |

## 공식 설치·호환성 근거와 현재 차단 이유

NVIDIA의 현재 [Isaac Sim 요구사항](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html)은 Ubuntu 24.04를 지원 OS로, Linux driver `595.58.03`을 테스트한 버전으로, RTX 5080을 good GPU 예시로 든다. RTX 5090을 명시적으로 테스트했다고 확인하는 문구는 이번 공식 문서에서 찾지 못했다. 그러므로 이 시스템의 RTX 5090에 대해 선택할 Isaac Sim 버전의 실행 호환성을 주장하지 않는다. 현재는 그 이전 단계인 driver user-space 접근이 실패한다.

공식 [Quick Install](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/quick-install.html)은 Linux standalone package 다운로드·압축 해제·`post_install.sh`·`isaac-sim.sh` 실행을 안내하며, 다운로드와 추출에 함께 약 40 GB가 들 수 있고 최소 50 GB 여유 공간을 권장한다. 현재 공간은 그 기준을 넘지만, 이 작업 범위에서는 설치·다운로드·시스템 driver 변경을 하지 않는다. 별도 Isaac Sim standalone/Kit runtime과 그 안의 URDF importer가 필요하며, 기존 `physxgen` 환경에 패키지를 섞는 것은 기존 재현 환경을 보존해야 하는 조건과 충돌할 위험이 있다.

공식 [URDF import 튜토리얼](https://docs.isaacsim.omniverse.nvidia.com/latest/importer_exporter/import_urdf.html)은 `isaacsim.asset.importer.urdf` extension과 USD 출력 경로를 요구한다. 물리 대조군이 재개되면 importer가 실제로 enable되는지, collider가 존재하는지, fixed base 및 유한 drive 설정이 기록되는지를 실행 전에 검사해야 한다.

## GT-only 대조군의 계획된 입력과 경계

향후 허가된 실행에서는 아래 **GT 파일만** converter/simulator 대조군으로 사용한다. 이들은 AI 생성 결과나 자동 예측군의 빈칸을 채우지 않는다.

| 사례 | GT 구조 | 이번 접근 | 실행 상태 |
| --- | --- | --- | --- |
| 10163 | fixed base + group 1 C-type rotation | `finaljson/10163.json`, part OBJ 2개 해시 일치 | 미시작 |
| 29806 | fixed base + group 1–3 C-type rotation | `finaljson/29806.json`, part OBJ 8개 해시 일치 | 미시작 |
| 29354 | 고정 대조 | `finaljson/29354.json`, part OBJ 6개 해시 일치 | 미시작 |

공식 source `sources/physx-4f54e750a309/urdf_gen.py`는 GT 전용 대조군 도구다. `./physxnet/finaljson`과 `./physxnet/partseg`를 입력으로 두고(29–45행), part OBJ를 링크 visual로 참조한다(58–62, 79–83, 98–102행). 이어 `group_info`에서 parent와 타입을 읽고(109–116행), B형의 axis/limit(131–142행) 및 C형의 origin/axis/limit(144–160행)을 URDF에 작성한다. 즉 generated mesh/property/group 출력만을 입력으로 받는 변환기가 아니다.

자동 예측군의 기존 판정은 유지한다.

| 자동 예측군 | 판정 | 이유 |
| --- | --- | --- |
| 10163 | `INTERPRETATION_BLOCKED` | parent/type/axis/origin/limit의 출력 해석 규약, 좌표계, 단위가 공개적으로 확인되지 않음 |
| 29806 | `INTERPRETATION_BLOCKED` | 위와 같음 |
| 29354 | `NO_DEPLOYABLE_JOINT_SPEC` | 배포 가능한 관절 명세가 원시 출력에서 확보되지 않음 |

따라서 자동 예측군은 이번에도 URDF/USD로 변환하지 않았다.

## 재개 전 최소 조건과 향후 시험 규약

아래 조건이 모두 충족되고 별도 실행 승인이 있을 때만 GT-only 대조군을 시작한다.

1. `nvidia-smi`와 Isaac Sim compatibility check가 정상이며, 실제 Isaac Sim/Kit 버전과 `isaacsim.asset.importer.urdf` extension 상태를 기록한다.
2. 새 격리 경로에만 GT-only URDF/USD와 실행 로그를 만들고, 기존 source·checkpoint·generated artifact를 바꾸지 않는다.
3. GT의 parent/type/axis/origin/limit만 사용한다. fixed base, 명시적 collider, 유한 joint drive를 설정하며, 공통 질량·관성·마찰을 쓸 경우 **통제된 실험 설정**으로 표시한다.
4. 관절별 목표 위치 5개, 왕복 10회, 초기화 3회, 범위 내/범위 밖 목표를 분리해 물리적으로 구동한다. 프레임 transform을 강제로 덮어쓰는 애니메이션은 사용하지 않는다.
5. command, Isaac/extension version, drive, joint state, collider/contact 상태, 실패 로그와 실제 물리 영상만 기록한다. 결과는 GT converter/simulator 대조군이며 AI 예측 성공이 아니다.

## 교차 확인 체크리스트

| 확인 항목 | 수현 담당: 예측 필드 감사 | 승민 담당: GT 대조군·Isaac 실행 | 합동 판정 |
| --- | --- | --- | --- |
| generated-output 경계 | 10163·29806 `INTERPRETATION_BLOCKED`, 29354 `NO_DEPLOYABLE_JOINT_SPEC` 유지 | GT-only 경로가 generated 결과를 읽거나 보완하지 않음 | GT→예측 누출 없음 |
| GT 입력 | 예측 산출물과 GT 입력을 별도 경로·해시로 식별 | `finaljson/group_info/partseg` 해시 재검증 | 대조군 입력 고정 |
| 변환 환경 | 예측 변환을 실행하지 않음 | Isaac/Kit, importer, driver, USD 출력·collider를 실제 확인 | 실행 사전조건 충족 여부 |
| 물리 구동 | 자동 예측 정확도로 해석하지 않음 | drive/target/state/contact을 기록하고 transform 강제 애니메이션 배제 | 실제 물리 구동 여부 |
| 보고 | AI 결과와 GT 대조군을 분리 | GT-only 실패를 모델 실패로 해석하지 않음 | 최종 문구 교차 검토 |

## 이번 미완료 항목

- Isaac Sim/Kit 및 URDF importer의 실제 설치·버전·enable 확인
- NVIDIA driver user-space 접근 정상화 여부 확인
- GT-only URDF 생성, USD import, collider/drive 설정, joint motion/contact 시험 및 실제 물리 영상
- generated-output 자동 관절 변환(공식 변환 규약 또는 검증 가능한 field/frame/unit 설명이 생기기 전까지 중단 유지)
