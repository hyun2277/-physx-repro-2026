# 29354 implicit_gemm runner

```bash
/home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/자료확보/run_inference_29354_implicit_gemm.sh
```

이 명령은 source 밖 timestamp staging에 `example.py` 복사본을 만들고 line 3만 `implicit_gemm`으로 바꾼 뒤 diff를 검사한다. 보호 검사를 모두 통과할 때만 GPU 1에서 한 번 실행하며, native 논문 실행이나 정량평가 결과를 의미하지 않는다.
