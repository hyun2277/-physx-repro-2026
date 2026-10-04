# 29806 initialization isolation과 10163 성공 경로 비교

## 최신 차등 실험 판정

`20261004T231747Z-...`의 visibility isolation은 유효하다. 모든 `Set()` 호출 8건이 성공했고 session layer `anon:...`가 edit target이었다. source-only는 clone 8개 `invisible`, 각 door phase는 해당 clone 1개만 `inherited`, base phase는 5개, all은 8개였다. source-only 반복은 다시 8개 `invisible`이고 첫 source-only와 사실상 동일했다.

| phase | 실제 composed clone | 화면 |
|---|---:|---|
| source-only | 0 inherited / 8 invisible | 검정, 원본 source 표면 없음 |
| source+red | red 1개 | 검정, red clone 표면 없음 |
| source+green | green 1개 | 초록 면과 수평 줄무늬 |
| source+blue | blue 1개 | 정상 단색 파랑 면 |
| source+base | base 5개 | 흰 수납장 윤곽 |
| source+all | 8개 | red 없음, green 줄무늬, blue 단색, base 윤곽 |
| source-only repeat | 0개 | 첫 source-only와 동일 |
| restored full | 8개 | source+all과 같은 이상 표시 |

따라서 source와 clone의 동시 렌더에 의한 z-fighting은 배제된다. 초록 줄무늬는 green clone 하나만 표시해도 존재하며, red clone 하나만 표시하면 표면이 나오지 않는다. 동일 camera에서 blue clone은 정상이라 공통 camera/clipping 실패도 배제된다. red/green 개별 geometry·material·Fabric presentation 중 어느 층이 원인인지는 아직 분리되지 않았다.

## 10163 성공 runner와 비교

10163 성공 실행은 commit `991286cf752abebf87b24e0b1da3a9b241b79568`, script SHA256 `bf023671a36455557482b75af97b9535a39b21ea73a1b072b04c070f3b871700`의 현재 저장 코드와 동일하다. 선택 경로는 `B_RELATIONSHIP_LINKED_CLONE`이다.

| 항목 | 10163 성공 | 29806 현재 |
|---|---|---|
| 입력 | GT USD, Physics=physx | GT USD, Physics=physx |
| visual mapping | relationship/fixed graph로 body 확정 | 세 body1와 fixed graph로 component 확정 |
| clone 좌표 | body-local points, identity local xform | 같은 원리, source↔clone 약 `4.93e-11 m` |
| clone parent | 실제 rigid body 2개 | base/door 실제 rigid component 8개 |
| source proxy 수정 | 없음 | 없음 |
| material | 단일 cyan PreviewSurface, diffuse+opacity | base/door 4색 PreviewSurface, diffuse+emissive+opacity |
| purpose/extent | 별도 명시 없음 | default purpose와 extent 명시 |
| physics init | initialize 후 update_fabric step 1, tensor view | initialize 내부 manager 2 후 tensor view/capture |
| tensor | 1 DOF | 3 DOF, runtime index 재검증 |
| stepping | `SimulationManager.step(update_fabric=True)` | 동일 |
| UI update | 각 step 뒤 `next_update_async()` | 동일 |
| pacing | responsive task, capture 구간 pace | strict recovery 전 bounded diagnostic |
| clone animation | xform/timeSample 추가 0 | xform/timeSample 추가 0 |

즉 노트북에서 성공한 핵심인 relationship-derived body-local clone은 이미 29806에도 적용됐다. 새로 복사할 mapping 알고리즘이 남은 것이 아니다. 가장 좁은 미검증 차이는 10163의 diffuse-only 단일 material과 29806의 문별 emissive material, 그리고 3문/8 mesh Fabric population이다.

다음 bounded diagnostic는 red/green/blue geometry와 parent를 그대로 둔 채 각 문에 10163과 동일한 diffuse-only cyan material을 한 번씩 적용한다. red가 cyan으로 나타나면 red material 경로, green 줄무늬가 사라지면 green material 경로가 원인이다. 같은 이상이 유지되면 geometry/Fabric population 쪽으로 좁혀진다. active target, recorder, MP4/GIF, 29354는 실행하지 않는다.
