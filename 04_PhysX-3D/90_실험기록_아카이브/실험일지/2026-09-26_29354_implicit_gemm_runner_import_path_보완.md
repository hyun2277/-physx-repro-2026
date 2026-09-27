# implicit_gemm runner import 경로 보완

staging 복사본 실행 시 `ModuleNotFoundError: No module named 'trellis'`가 발생한 원인을 반영해 runner의 실제 example 프로세스에만 `PYTHONPATH="$SRC${PYTHONPATH:+:$PYTHONPATH}"`를 추가했다. 원래 `PYTHONPATH`가 있으면 source 경로를 앞에 두고 뒤 값을 보존한다. source와 staging 복사본은 수정하지 않았다.

GPU 없는 정적 검증에서 지정 Python의 `importlib.util.find_spec('trellis')`가 고정 source의 `trellis/__init__.py`를 가리켰고, staging example의 AST 파싱 및 native→implicit_gemm 변경이 line 3 한 줄뿐임을 다시 확인했다. 실제 `import trellis`는 Warp가 cache/GPU 초기화를 시도해 현재 장치 없는 환경에서 중단되므로 실행하지 않았고, 이 과정에서 GPU나 `example.py`는 실행하지 않았다.
