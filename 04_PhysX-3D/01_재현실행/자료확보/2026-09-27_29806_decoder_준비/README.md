# 29806 C형 회전 관절 decoder 준비

29806 sampling-only run `20260926T220010Z-ac2c1dfab94d`는 성공했다. 저장 latent는 N=11,216, 최대 subdivision point 수 N×64=717,824이며 SHA256은 `28892598d421e93566b1053a9eff72704f6602a995709e848532090d883a2fff`다. 관측 기반 예상 peak+오차는 11,268.889 MiB로 28,000 MiB 상한과 4,607 MiB reserve 조건을 충족한다.

## GT 구조

- group 0 fixed base: parts 0, 4, 5, 6, 7
- group 1: door part 1, parent 0, type C rotation, direction `[0,1,0]`, position `[0.81483944,0.29875061,-0.22010788]`, range `[-1,0]`
- group 2: door part 2, parent 0, type C rotation, direction `[0,1,0]`, position `[0.25272892,0.30850974,-0.22462723]`, range `[-1,0]`
- group 3: door part 3, parent 0, type C rotation, direction `[0,1,0]`, position `[-0.27846661,-0.31798351,-0.22822706]`, range `[-1,0]`

이 값은 GT annotation의 구조다. 생성 mesh 정점과 GT part 사이의 공식 직접 대응이 확인되지 않으면 예측 parent, direction, position, range의 정확도를 주장하지 않는다.

## 실행기

29806 wrapper는 24566에서 성공한 다음 안전장치와 구현을 그대로 사용한다.

1. 기존 sampling stage 1–6 SUCCESS marker, input fingerprint, 모든 output size/SHA256, latent hash 재검증
2. GPU 1 compute-process 보호, 28,000 MiB 상한, 4,607 MiB reserve, proactive memory guard
3. 검증된 input/output channel tiling과 memory-bounded GroupNorm의 작은 GPU 동등성 검사
4. physics와 mesh decoder를 별도 child process로 실행
5. mesh/raw physics/property head 결과를 CPU에서 다시 열고 공식 group 결과와 별도 indexing 수정 후보를 분리 저장

실행기에는 Git 동작이 없다. description, density·affordance 정확도, 30-view PSNR과 논문 전체 정량평가는 범위 밖이다. 기존 24566 결과와 false-negative 기록은 수정하지 않는다.

```bash
/home/minsujo/Desktop/SH/PHYSx/envs/physxgen/bin/python -B /home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/01_재현실행/자료확보/run_articulated_decoder_29806.py
```
