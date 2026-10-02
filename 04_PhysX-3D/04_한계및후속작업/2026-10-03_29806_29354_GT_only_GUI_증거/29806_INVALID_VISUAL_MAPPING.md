# 29806 첫 GUI 시도: INVALID_VISUAL_MAPPING

실행은 수치상 세 DOF를 움직였지만 사람이 본 화면에서 세 문이 각 위치에서 독립적으로 보이지 않았다. 자동 video validator도 `FAIL`이었다. 따라서 MP4는 staging에만 보존하며 공식 링크·GIF·PASS로 사용하지 않는다.

확인된 관계는 공통 body0 `.../l_0`, 서로 다른 body1 `.../abstract_1`, `abstract_2`, `abstract_3`이다. source Mesh 기록도 `abstract_1/l_1`, `abstract_2/l_2`, `abstract_3/l_3`을 각각 door component에 연결했다. 그러나 첫 marker는 원래 rigid ancestor와 source/reconstructed world bounds를 저장하지 않았고 모든 component를 같은 청록색으로 표시했다. 따라서 관계 graph가 맞다는 사실만으로 화면 배치가 맞다고 판정할 수 없다.

새 static gate는 physics·timeline·tensor·capture 없이 다음을 먼저 검증한다.

- source Mesh의 실제 최근접 rigid ancestor
- joint/fixed graph로 도출한 target component
- mesh별 source world bounds와 body-local 재구성 world bounds
- round-trip 오차
- stage meters-per-unit/up-axis와 joint local frame
- 회색 base, 빨강 `gt_C_1`, 초록 `gt_C_2`, 파랑 `gt_C_3`
- 전체 bounds에서 도출한 정면 camera

사람이 base와 서로 다른 위치의 문 세 개를 동시에 확인하기 전에는 physics runner의 차단을 해제하지 않는다.

## 20261002T193617Z static gate 재감사

실제 JSON은 `metersPerUnit=1`, `upAxis=Z`를 기록했다. 세 문 bounds는 X 방향으로 서로 다른 구간을 차지하지만 Z 두께는 각각 약 `0.0291`, `0.00560`, `0.00580 m`에 불과했다. 기존 camera 규칙은 Z를 up-axis라는 이유로 view 후보에서 제외하고 +Y를 선택했다. 이 시점은 문의 XY 넓은 면을 정면으로 보지 못하며, 사용자가 본 가느다란 수평선과 일치한다. 이는 camera 선택 오류로 **확정**한다.

기존 conditioning `006.png`도 가로로 긴 본체 앞면에 세 패널이 나란히 있는 형상을 보여 준다. 이 이미지는 camera 선택을 검산하는 참고 자료이며 Mesh나 joint mapping을 바꾸는 근거로 사용하지 않는다.

계산된 source와 reconstructed bounds는 모든 Mesh에서 일치했고 기록된 최대 round-trip 오차는 `5.551115123125783e-17 m`였다. 다만 이 기록은 clone authoring 전에 계산된 값이었다. 새 gate는 author된 clone prim을 stage에서 다시 읽어 모든 점과 world bounds를 source와 비교하며, ±X/±Y/±Z 실제 GUI 화면 여섯 장과 contact sheet를 만든다. 자동 검사는 비검정까지만 담당하고 component 가시성은 사람 확인 전까지 pending이다.
