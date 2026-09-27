# 로봇팔 제조 시뮬레이션 개념 시연

이 디렉터리의 영상은 제조 현장에서 물리 정보를 갖춘 3D 자산이 로봇 시뮬레이션에 왜 필요할 수 있는지를 보여 주기 위한 **시각적 개념 애니메이션**이다. 화면에 다음 문구를 계속 표시한다.

> Concept demonstration — not a PhysX-3D generated result

## 제작물

| 파일 | 형식·길이 | 크기 | SHA256 |
| --- | --- | ---: | --- |
| `robot_arm_manufacturing_concept.mp4` | H.264, 960×540, 12 fps, 12.0 s | 52,384 bytes | `7090b23b3a48e6914688fd7927f7969f98ec4a95e1814495e91724c71397bb54` |
| `robot_arm_manufacturing_concept_poster.png` | PNG, 960×540 | 111,716 bytes | `5b2d8f2836ee237025238c94eccdb8989a33463541aa72b0f1e3f2aa0c03ebef` |

## 도구와 자산

- 도구: 로컬 portable Blender 3.0.1 (`/home/minsujo/Desktop/SH/PHYSx/tools/blender-3.0.1/unpacked/blender-3.0.1-linux-x64/blender`)과 로컬 `ffmpeg 6.1.1`.
- 자산 출처: Blender 안에서 새로 만든 cube, cylinder, empty 기본 도형뿐이다. 외부 로봇 모델, URDF, PhysXNet JSON, PhysX-3D 생성 mesh, checkpoint는 사용하지 않았다.
- 사전 읽기 전용 점검에서 로컬 MuJoCo, PyBullet, Isaac Sim 실행 환경은 확인되지 않았다. 다른 재현 기록의 URDF도 출처·라이선스가 이 시연 용도로 확인되지 않아 사용하지 않았다.

## 표현 범위

작업대, 절차적 로봇팔, 작업물의 위치와 관절 회전은 Blender keyframe transform으로 만든 시각 효과다. 물리 엔진, 충돌, 접촉, 질량·관성, 제어기, URDF 또는 실제 관절 동역학을 계산하지 않았으므로 이 영상은 **physics simulation이 아니다**.

이 시연은 PhysX-3D 또는 PhysXNet이 로봇팔을 생성하거나 로봇 관절을 예측한 결과가 아니다. 공개 PhysXNet test JSON에서 적격 로봇팔 표본을 확인하지 못한 기존 읽기 전용 조사 결과도 그대로 유지한다. 따라서 관절 정확도, 힌지 동작, 제조 자산 적합성, 논문 정량평가의 근거로 사용하면 안 된다.
