# 교수님 질문 답변

1. **실제 Isaac 3D 구동 영상:** 아직 없다. 통합 runner 실행과 사람 확인 뒤에만 기록한다.
2. **검은 화면 당시 값:** tensor target/readback, measured position/velocity, PhysX step counter로 확인했다. state-trace MP4는 그래프다.
3. **이슈:** [ISSUE_LEDGER.md](ISSUE_LEDGER.md)에 physics 전/중을 구분했다.
4. **USD 로딩:** Python runner가 해시 검증된 GT USD를 `omni.usd` API로 직접 연다. File 메뉴 방식이 아니다.
5. **GUI:** GPU 0 cube와 static CloneMesh는 사람이 확인했지만 실제 physics 영상은 확인 전이다.
6. **Warp:** articulation target 설정과 state readback에만 쓴다. transform/keyframe은 쓰지 않고 authored 속성을 전후 비교한다.
7. **증거:** USD SHA, schema, relationship mapping, 향후 screenshot/video SHA를 연결한다. Windows-only screenshot을 Linux/Git 파일로 주장하지 않는다.
8. **범위:** 입력은 GT URDF/USD뿐이다. generated output은 사용하지 않으며 제목에 `not AI prediction`을 표시한다.
