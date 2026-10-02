# Replicator RGB smoke 차단 기록

이 기록은 10163 GT-only 물리 구동 PASS를 바꾸지 않는다. 10163 USD와 관절 제어는 이번 시도에서 열지 않았다.

`isaac_minimal_replicator_render_r11.kit`은 Isaac Sim 6.1 설치본의 Replicator 예제와 `omni.replicator.core` renderer test를 근거로, Replicator·viewport window·Hydra RTX·PhysX/tensors만 선언한다. ML, ROS, `omni.isaac.ml_archive`는 선언하지 않았다. GPU는 Isaac의 물리 GPU 1만 직접 선택했고 multi-GPU는 껐다.

공식 예제 순서대로 새 stage, dome light, cube, camera, render product, RGB annotator, BasicWriter를 만들고 `step_async()`를 세 번 수행했다. Writer PNG 3장과 annotator PNG 3장은 생성됐지만, annotator RGB 세 장은 모두 512×512, RGB 평균 `[0,0,0]`, 분산 `0`, 최대값 `0`이었다. 따라서 smoke는 `BLOCKED_RGB_BLACK`이며, 10163을 열거나 physics drive/MP4를 만들지 않았다.

r11 stderr의 최초 실패는 smoke 검증 코드의 `RuntimeError: black/constant RGB frames`다. r11에는 누락 extension 또는 Python import traceback이 없었다. 별도 r8 시도는 base experience가 필수 의존성인 `omni.isaac.ml_archive`를 다시 시작하며 알려진 `libc10_cuda.so` CUDA ABI 오류를 재현해 폐기했다.

다음 단계는 10163 재실행이 아니라, NVIDIA 지원 범위의 Isaac 6.1 headless RTX render delegate/device 진단이다. 기존 검은 viewport MP4는 `INVALID_BLACK_CAPTURE`로 그대로 보존한다.

세부 경로·SHA256·명령·stderr 근거는 [replicator_rgb_smoke_failure.json](replicator_rgb_smoke_failure.json)에 있다.
