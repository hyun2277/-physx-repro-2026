# 10163 GT-only Isaac Sim GUI physics video

상태: **AUTOMATION_PASS_HUMAN_CHECK_REQUIRED**. GT-only 변환기·Isaac Sim 대조군이며 PhysX-3D 자동 예측 성공이 아니다.

- MP4: `10163_gt_only_gpu0_gui_physics.mp4` (897,661 bytes, SHA256 `d78beb9540695885f6b1ad752181aeb9cf4d3fd588f7dcc18de24efbf8aa02a9`)
- H.264/yuv420p, 1920×1080, 30 fps, 23.2 s, 696 frames
- capture physics records: 450; manager steps 243→693
- measured joint span: 1.218261227 rad
- start/middle/end measured positions: 0.038234830, -1.174542546, 0.038168352 rad
- clone xform author after start: 0; timeSample author after start: 0

세 대표 프레임은 모두 비검정이며 Isaac Sim 창, Stage tree의 `gt_C_1`, Base/Lid 표면을 보여 준다. 중간 프레임은 열린 자세이고 시작·끝은 닫힌 자세다. 픽셀 차이 및 physics record 대응도 통과했다. 사용자가 실행 중 표면과 힌지 움직임을 관찰했으므로 `HUMAN_OBSERVED_DURING_RUN`으로 기록한다. 저장 MP4 전체를 사람이 직접 검토하기 전까지 최종 human PASS로 올리지 않는다.

종료 시 `Unexpected reference count ...` 경고가 원문 로그에 한 번 있다. 성공 marker 뒤 shutdown 중 발생했고 exit 0, `COMPLETE`, report/MP4/validation이 모두 존재하므로 이 실행을 무효화한다는 증거는 없다. 경고를 정상으로 일반화하지는 않는다.
