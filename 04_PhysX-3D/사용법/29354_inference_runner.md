# 29354 pretrained inference runner

Linux 일반 터미널에서 PHYSx 작업 폴더를 기준으로 다음 한 줄을 실행한다.

```bash
/home/minsujo/Desktop/SH/PHYSx/repro-records/04_PhysX-3D/자료확보/run_inference_29354.sh
```

실제 경로의 디렉터리 이름은 `04_PhysX-3D`이다.

runner는 source HEAD와 staged/unstaged tracked 변경을 검사하고 `trellis/**/__pycache__/*.pyc`만 허용한다. 29354 입력·transforms·checkpoint manifest hash, GPU 1 UUID와 compute-process 부재를 확인한 뒤에만 `CUDA_VISIBLE_DEVICES=1`로 source의 공식 `example.py`를 한 번 실행한다. 출력과 모든 로그는 새 timestamp 경로에 만들며 Git push는 수행하지 않는다. 결과 검증은 네 MP4의 `ffprobe` 기본 디코딩과 `texture.glb` 헤더 확인만 한다.
