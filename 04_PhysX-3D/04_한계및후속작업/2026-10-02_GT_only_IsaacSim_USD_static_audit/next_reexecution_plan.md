# 최소 재검증 계획

1. 기존 `20261002T072614Z-gt-only-control` staging을 그대로 사용한다. URDF 생성과 USD import를 반복하지 않는다.
2. `10163`, `29806`에는 root prim의 `Physics=physx`를 명시하고, `29354`에는 `Physics=physics`를 명시해 composed stage의 `UsdPhysics.RevoluteJoint`/`UsdPhysics.Joint`, articulation root, collision, rigid-body API를 검사한다.
3. 기대 schema count는 10163=1 revolute, 29806=3 revolute, 29354=0 revolute 및 fixed-joint-only이다. 다르면 physics drive를 시작하지 않고 USD composition/importer configuration을 다시 감사한다.
4. 이 검사가 통과한 뒤에만 별도 실행에서 GT-only drive/contact 시험을 한다. 자동 예측 출력, GT-to-prediction 복사, 수동 joint authoring은 계속 금지한다.
