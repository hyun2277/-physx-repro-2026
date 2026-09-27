# 공식 예제 1개용 모델 준비 검토

2026-09-21 작성. 이 준비 단계에서는 모델 다운로드 실행기만 작성했고 가중치를 다운로드하거나 모델을 import/실행하지 않았다. `prepare_models.py`의 Python AST와 JSON 구조를 읽기 전용으로 확인했다. 실행기 자체의 실행 검증은 아직 하지 않았다.

## 고정 입력과 저장 경로

- PhysX 원본: `4f54e750a309fe9cd9f20816916ecc0e8a9ae594`.
- [Caoza/PhysXGen metadata](https://huggingface.co/api/models/Caoza/PhysXGen/revision/52598097b7092df495ac149e137050ce2d2784fe?blobs=true): diffusion/pipeline.json + ckpts_new의 JSON/PT 5쌍, 총 11개. `sources/physx-4f54e750a309/pretrain` 아래에 원래 상대 경로로 배치한다.
- [microsoft/TRELLIS-image-large metadata](https://huggingface.co/api/models/microsoft/TRELLIS-image-large/revision/25e0d31ffbebe4b5a97464dd851910efc3002d96?blobs=true): ss_dec, ss_flow, slat_dec_gs, slat_dec_rf 각각 JSON/safetensors 2개, 총 8개. `pretrain/trellis/ckpts` 아래에 배치한다.
- HF 선택 합계는 9,543,576,141 bytes다. 표준 `hf_hub_download(token=False)` cache를 사용한 뒤 검증된 파일을 목적지에 복사하므로 cache 공간도 별도로 필요하다. LFS 파일은 공식 SHA256/크기, JSON은 공식 Git blob SHA1/크기를 검증하고 실제 SHA256도 기록한다.
- [고정 OpenAI CLIP](https://github.com/openai/CLIP/blob/d05afc436d78f1c48dc0dbf8e5980a9d471f35f6/clip/clip.py)의 ViT-L/14 URL parent SHA256 `b8cca3fd41ae0c99ba7e8951adf17d267cdb84cd88be6f7c2e0eca1737a03836`을 검증한다. `cache/clip/ViT-L-14.pt`, HEAD 크기 932,768,134 bytes. CLIP 기본 경로는 XDG만으로 바뀌지 않으므로 root 소유 패치에서 `download_root=os.environ["PHYSX_CLIP_DOWNLOAD_ROOT"]`를 전달해야 한다.
- DINO 가중치는 `cache/torch/hub/checkpoints/dinov2_vitl14_reg4_pretrain.pth`, HEAD 크기 1,217,607,321 bytes다. 총 21개 파일의 payload는 11,693,951,596 bytes다. 빌드/결과/임시 공간은 이 합계에 포함하지 않았다.

## DINO 소스 고정 제안과 한계

PhysX는 `torch.hub.load('facebookresearch/dinov2', name, pretrained=True)`로 GitHub 소스 revision을 고정하지 않는다. [공식 register 모델 도입 commit](https://github.com/facebookresearch/dinov2/commit/9c7e3245797cf7be5b5729445a4af1272bd610df)을 명시적인 재현 선택으로 고정하는 안이다. 이는 원본 PhysX가 사용한 DINO revision을 소급 확인했다는 뜻이 아니다.

해당 소스의 `hubconf.py`, `dinov2/hub/backbones.py`, `dinov2/hub/utils.py`, `dinov2/layers/attention.py`를 원문으로 읽었다. `dinov2_vitl14_reg`는 register 4개 모델이고 공식 코드가 구성하는 URL은 다음과 같다.

`https://dl.fbaipublicfiles.com/dinov2/dinov2_vitl14/dinov2_vitl14_reg4_pretrain.pth`

공식 HEAD 크기를 확인했으나 검토한 공식 소스에 SHA256은 없다. multipart S3 ETag를 SHA256으로 취급하지 않는다. 다운로드 후 SHA256을 로컬 provenance로 기록하며, 처음부터 upstream digest에 맞췄다고 주장하지 않는다. 재실행 시 기존 파일은 로컬 receipt의 SHA256까지 맞아야 재사용한다.

root가 소스를 `sources/dinov2-9c7e3245797c`에 고정하여 받은 뒤, PhysX 코드를 `torch.hub.load(<절대 로컬 경로>, name, source='local', pretrained=True)`로 바꿀 수 있다. `TORCH_HOME=ROOT/cache/torch`와 가중치 사전 배치가 필요하다. HF offline 설정만으로 torch.hub의 GitHub/가중치 요청이 차단되지는 않으므로 실제 GPU 실행은 별도 offline namespace를 사용해야 한다. 이 실행기는 DINO 소스를 clone하거나 원본 코드를 변경하지 않는다.

선정 소스는 xformers가 없으면 ordinary Attention으로 처리한다. 소스 선택 및 라이브러리 호환성이 실제 추론에서 성공하는지는 아직 검증하지 않았다. 최신 DINO의 `torch.__version__ >= (2,1)` 비교를 오류로 의심했던 초기 의견은 철회했다. 설치된 PyTorch의 `TorchVersion`은 tuple 비교를 명시적으로 지원한다.

## table.png의 rembg 분기

로컬 원본 이미지의 Pillow decode만 수행했다. SHA256 `67ce4c07693c8814dbdb068c7184b3b6341dc8fd7a595cdaef314d0fb1c2b388`, 483,075 bytes, RGBA 1024×1024, alpha 범위 0–255, alpha<255 픽셀 1,030,547개, alpha>204 픽셀 19,148개다. 고정 PhysX의 `preprocess_image`는 nonopaque RGBA를 바로 사용하므로 이 입력에는 `rembg.new_session('u2net')`을 호출하지 않는다. 경계 상자에 쓸 alpha 픽셀도 비어 있지 않다. 다른 입력으로 이 판단을 일반화하지 않는다.

초기 image-only probe는 system Python3.12에서 target Python3.10 Pillow를 읽으려다 `_imaging` import 오류가 났다. 동일 읽기 전용 검사를 target Python3.10으로 수행해 성공했다. 설치나 환경 변경은 없었다.

## 실행과 기록

`model-source-preparation-review.json`에 검토 시 파일 hash와 실행 명령 배열이 있다. root가 검토 후 `workspace_runner.py --execute --profile download`로 실행한다. GPU 장치를 숨기고 Python 환경/Toolkit을 읽기 전용으로 두며 ROOT 내 cache/목적지만 쓴다. 기존 파일의 hash/크기가 다르면 덮어쓰지 않고 중단한다. 원본 source, 모델 import, 설치, 빌드, GPU 실험은 이 다운로드 실행기에 없다.

각 파일 작업의 stdout/stderr/operation/result를 `model-downloads/<run-id>/<number>-<filename>/`에 남기고 실제 프로세스 exit은 바깥 workspace runner가 기록한다. 완료 파일은 `model-download-receipt.json`에 순차 기록한다. 실패 시 부분 파일과 완료 receipt를 보존하며 자동 작업 재실행이나 보호 완화는 하지 않는다. HF 라이브러리 내부의 기본 네트워크 재시도 동작까지 없다고 주장하지 않는다. 공개 다운로드만 사용하고 `token=False`, implicit token 비활성화, token path `/dev/null`, signed-query URL의 로그 제거를 적용한다.

파일 다운로드/해시 성공은 역직렬화, GPU 추론, 논문 결과 재현의 성공을 뜻하지 않는다.
