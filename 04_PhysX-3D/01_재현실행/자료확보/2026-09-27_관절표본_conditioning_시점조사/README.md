# 24566·29806 conditioning 입력 시점 조사

이 기록은 이미 생성된 24-view conditioning PNG와 `transforms.json`만 CPU에서 읽었다. 새 Blender 렌더링, GPU 실행, 모델 추론은 수행하지 않았다. 각 표본은 24개 frame을 가지며, 모든 PNG는 실제 PNG로 디코드했고, `transforms.json`의 frame 경로 집합·4×4 camera matrix 유한성·각 PNG의 존재와 SHA256을 확인했다. 실제 추론 입력은 두 표본 모두 `000.png`이며 contact sheet에서 빨간 테두리로 표시했다.

| object | GT 이동 구조 | `000.png` 관찰 | 시각적으로 더 드러나는 후보 |
| --- | --- | --- | --- |
| 24566 | group 1, part 5, B형 translation drawer | 어두운 직사각형 drawer-front가 밝은 fixed frame과 분리되어 큰 면적으로 보인다. 다만 위쪽의 사선 시점이라 fixed legs·shelf도 함께 보인다. | `001.png`: drawer-front와 주변 frame의 경계가 더 정면에 가깝게 보인다. |
| 29806 | groups 1·2·3, parts 1·2·3, C형 rotation doors | 거의 끝면에 가까운 세로 시점이라 각 door의 전면 seam을 구분하기 어렵다. | `006.png`, `012.png`: 세 개의 전면 panel과 seam이 더 넓게 보인다. |

후보의 “더 잘 보임”은 contact sheet와 원본 PNG를 사람이 관찰해 기록한 것이다. 논문의 공식 평가 camera, 더 공정한 입력, 또는 더 높은 정확도를 보장하는 시점이라는 뜻은 아니다.

24566의 공식 결과는 GT drawer에 대해 `num_group=1`인 false negative였고, 29806은 GT 4 groups에 대해 공식 `num_group=2`인 group-count underprediction이었다. 이 문서는 두 결과가 각각 `000.png` 한 장을 조건으로 생성됐다는 점만 연결한다. 시점 관찰만으로 해당 실패의 원인이나 물체 전체에 대한 결론을 확정하지 않는다.

산출물:

- `24566_24view_contact_sheet.png`, `29806_24view_contact_sheet.png`: 24-view contact sheet.
- `conditioning_audit.json`: frame별 경로, hash, 크기, 카메라 변환과 검증 결과.
- `view_observations.csv`: GT 이동 part와 시각 관찰의 짧은 대응표.
