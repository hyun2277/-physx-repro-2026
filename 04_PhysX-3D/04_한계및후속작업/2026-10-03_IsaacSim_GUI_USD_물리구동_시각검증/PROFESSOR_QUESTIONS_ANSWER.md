# 교수님 질문 답변

1. **실제 Isaac 3D 구동 영상:** `20261002T184456Z_10163_GT_only_GUI_physics_video/10163_gt_only_gpu0_gui_physics.mp4`에 있다. 자동검증은 통과했고 저장 MP4 전체의 사람 검토는 대기 중이다.
2. **검은 화면 당시 값:** tensor target/readback, measured position/velocity, PhysX step counter로 확인했다. state-trace MP4는 그래프다.
3. **이슈:** [ISSUE_LEDGER.md](ISSUE_LEDGER.md)에 physics 전/중을 구분했다.
4. **USD 로딩:** Python runner가 해시 검증된 GT USD를 `omni.usd` API로 직접 연다. File 메뉴 방식이 아니다.
5. **GUI:** GPU 0에서 실행 중 노트북 표면과 힌지 움직임을 사람이 관찰했다(`HUMAN_OBSERVED_DURING_RUN`). 저장 MP4는 대표 프레임 자동·직접 검사를 통과했지만 전체 인간 검토 전이다.
6. **Warp:** articulation target 설정과 state readback에만 쓴다. transform/keyframe은 쓰지 않고 authored 속성을 전후 비교한다.
7. **증거:** USD SHA, schema, relationship mapping, 향후 screenshot/video SHA를 연결한다. Windows-only screenshot을 Linux/Git 파일로 주장하지 않는다.
8. **범위:** 입력은 GT URDF/USD뿐이다. generated output은 사용하지 않으며 제목에 `not AI prediction`을 표시한다.
