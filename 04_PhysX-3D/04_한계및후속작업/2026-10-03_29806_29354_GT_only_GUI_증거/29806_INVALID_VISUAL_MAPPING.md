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
