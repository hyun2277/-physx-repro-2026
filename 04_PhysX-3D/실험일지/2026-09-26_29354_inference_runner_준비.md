# 29354 pretrained inference runner 준비

사용자 일반 Linux 터미널에서만 실행할 runner를 추가했다. source HEAD 고정값, staged/unstaged tracked 변경 검사, `trellis/**/__pycache__/*.pyc`만 허용하는 목록 검사, 29354 입력·transforms hash, checkpoint manifest hash, GPU 1 UUID 및 compute-process 보호를 실행 전에 수행한다. 통과할 때만 공식 source의 `example.py`를 `CUDA_VISIBLE_DEVICES=1`로 한 번 실행하며, 새 timestamp 출력·로그를 사용한다.

이번 작업에서는 GPU와 `example.py`를 실행하지 않았다. `bash -n`, source 경로 분류 mock, checkpoint manifest read-only hash 검증만 수행했다. runner에는 Git push 동작이 없고, 생성 영상·GLB·캐시는 Git에 추가하지 않는다.
