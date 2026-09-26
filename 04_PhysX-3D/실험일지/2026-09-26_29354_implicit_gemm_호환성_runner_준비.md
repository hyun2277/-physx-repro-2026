# 29354 implicit_gemm 호환성 runner 준비

원본 `example.py:3`은 `os.environ['SPCONV_ALGO'] = 'native'`를 강제한다. source 밖의 timestamp staging에 복사본을 만들고 이 한 줄의 값만 `implicit_gemm`으로 바꾸는 runner를 추가했다. runner는 source HEAD, staged/unstaged tracked 변경에서 `trellis/**/__pycache__/*.pyc`만 허용하는 검사, 29354 입력·transforms hash, checkpoint manifest hash, GPU 1 UUID와 compute-process 보호를 그대로 유지한다.

사용자가 Linux 일반 터미널에서 runner를 실행할 때만 새 로그·출력 staging에서 복사본을 한 번 실행한다. 성공해도 결과는 `implicit_gemm 호환성 실행`으로만 해석하며 원본 native 실행·논문 정량평가 성공으로 확대하지 않는다. 이번 작업에서는 GPU와 `example.py`를 실행하지 않았고 `bash -n` 및 복사본 diff mock만 수행했다.
