# 쇼핑 쇼츠 무료 자동 생성 (Wan 2.2 + ComfyUI + edge-tts + ffmpeg)

힉스필드 크레딧 없이, **제품 사진 한 장**에서 세로 쇼핑 쇼츠를 만드는 파이프라인입니다.
영상 생성은 오픈소스 모델 **Wan 2.2**(Apache 2.0)를 ComfyUI 로 돌리고,
나레이션은 edge-tts, 합성은 ffmpeg 를 씁니다. 전부 무료이고 워터마크가 없습니다.

```
제품 사진 → [1] 시작 프레임 → [2] Wan 2.2 클립 (ComfyUI) → [3] 나레이션 (edge-tts) → [4] 합성 (ffmpeg) → final.mp4
```

| 단계 | 도구 | 비용 | 어디서 도는가 |
|---|---|---|---|
| 샷리스트(프롬프트+나레이션 대본) | Claude Code 직접 대화 (또는 Anthropic API) | 구독 안에 포함 | 내 PC |
| 시작 프레임 | Pillow | 무료 | 내 PC |
| 클립 생성 | ComfyUI + Wan 2.2 | 무료 | **내 GPU** 또는 **Kaggle 무료 GPU** |
| 나레이션 + 자막 | edge-tts | 무료 | 내 PC |
| 합성 | ffmpeg | 무료 | 내 PC |

## 무엇이 되고, 무엇이 안 되는가

- **손만 나오는 리뷰 (권장)**: 잘 됩니다. 제품 사진을 첫 프레임으로 놓고 "손이 들어와 제품을 든다" 같은
  동작을 프롬프트로 주면 Wan 2.2 가 손을 그려 넣습니다. 얼굴이 없으니 컷마다 다른 사람이어도 티가 안 납니다.
- **얼굴이 나오는 리뷰**: 됩니다만 손이 더 갑니다. 같은 인물이 컷마다 유지되려면 **인물 참조 사진 한 장**을
  먼저 준비해 face 샷의 `start_image` 로 넣어야 하고, 입을 맞춰 말하는 립싱크는 이 파이프라인에 없습니다
  (아래 "얼굴 컷" 참고).
- **속도**: 5초 클립 하나에 RTX 3060~4070 은 3~8분, Kaggle T4 는 10~15분입니다. 5컷짜리 쇼츠면
  로컬 30분, Kaggle 1시간 안팎입니다. 힉스필드보다 느린 대신 0원입니다.

## 사전 준비

### A. ComfyUI + Wan 2.2 (둘 중 하나)

**A-1. 내 PC에 NVIDIA GPU가 있을 때 (8GB VRAM 이상)**

1. [ComfyUI](https://github.com/comfyanonymous/ComfyUI) 설치 (윈도우는 포터블 zip 이 가장 쉽습니다)
2. 모델 3개를 받아 ComfyUI 폴더에 넣기 (총 약 17GB, [Comfy-Org/Wan_2.2_ComfyUI_Repackaged](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged) 의 `split_files/` 안)

   | 파일 | 넣을 곳 |
   |---|---|
   | `wan2.2_ti2v_5B_fp16.safetensors` | `ComfyUI/models/diffusion_models/` |
   | `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | `ComfyUI/models/text_encoders/` |
   | `wan2.2_vae.safetensors` | `ComfyUI/models/vae/` |

3. ComfyUI 를 API 를 열고 실행: `python main.py --listen` (포터블은 `run_nvidia_gpu.bat` 안의 명령에 `--listen` 추가)
4. 브라우저에서 `http://127.0.0.1:8188` 이 뜨면 준비 끝

VRAM 16GB 이상이면 화질이 더 좋은 14B 모델도 쓸 수 있습니다. `workflows/wan22_14b_i2v.json` 에 적힌
파일 4개(high/low noise 14B fp8, umt5, `wan_2.1_vae.safetensors`)를 받고 shotlist 의 `video.workflow` 를
`wan22_14b_i2v`, `length` 를 `81`, `fps` 를 `16` 으로 바꾸면 됩니다.

**A-2. GPU가 없을 때 — Kaggle 무료 GPU (주 30시간)**

1. kaggle.com 가입 후 휴대폰 인증 (GPU 사용 조건)
2. 새 노트북 → Settings 에서 Accelerator = **GPU T4 x2**, Internet = **On**
3. 셀에 아래 한 줄을 넣고 실행 (모델 다운로드 포함 10분 정도)
   ```
   !curl -sL https://raw.githubusercontent.com/kjr1728-glitch/ddong/main/shopping-shorts/kaggle/start_comfyui.sh | bash
   ```
4. 마지막에 찍히는 `COMFY_URL=https://xxxx.trycloudflare.com` 을 내 PC 의 `.env` 에 넣기

노트북을 닫으면 주소가 사라집니다. 다음에 또 쓸 때는 3~4번을 다시 하면 됩니다.
(Kaggle 은 실행 중인 노트북을 최대 12시간 뒤 종료하고, 30분 이상 아무 셀도 안 돌면 꺼집니다.
클립을 뽑는 동안은 이 파이프라인이 계속 요청을 보내므로 꺼지지 않습니다.)

### B. 내 PC 쪽 준비

```bash
cd ddong/shopping-shorts
pip install -r requirements.txt
cp .env.example .env        # COMFY_URL 확인 (로컬이면 그대로)
```

ffmpeg 는 시스템에 있으면 그걸 쓰고, 없으면 `imageio-ffmpeg` 가 내장 바이너리를 받아 씁니다.
한글 자막 폰트는 시스템에서 자동으로 찾습니다 (윈도우: 맑은 고딕, 맥: Apple SD Gothic).

## 사용 방법

### 1. 제품 사진 넣기
`assets/product.png` 에 저장합니다. 배경이 단순하고(흰색/단색) 제품이 가운데 있는 사진이 가장 잘 됩니다.
누끼 사진이면 더 좋습니다.

### 2. 샷리스트 만들기 (프롬프트 + 나레이션)
```bash
python scripts/write_shotlist.py --product "무선 전동 청소솔" \
    --features "버튼 하나로 작동,헤드 3종 교체,완전 방수" --shots 5 --style hand
```
출력되는 요청문을 **Claude Code 에 붙여넣고** 받은 JSON 을 `shotlist.json` 으로 저장합니다.
(무인 자동화가 필요하면 `--auto` 를 붙이면 Anthropic API 가 바로 만듭니다. 종량 과금)

형식은 `shotlist.example.json` 을 보면 됩니다. 손으로 고쳐도 됩니다.
- `type`: `hand`(손이 나옴) / `product`(제품만) / `face`(얼굴, 참조 사진 필요)
- `prompt`: 영어 동작 묘사. 카메라 움직임과 손동작을 구체적으로.
- `narration`: 한국어 대사. 샷당 12~25자가 5초에 맞습니다.

### 3. 점검 → 실행
```bash
python main.py --shotlist shotlist.json --check   # ComfyUI 연결, 모델 파일, ffmpeg 확인
python main.py --shotlist shotlist.json           # 전체 실행
```
`output/<날짜>_<제품명>/final.mp4` 가 결과입니다. 같은 폴더의 `final.srt` 는 유튜브 자막용입니다.

중간에 끊기면 같은 명령을 다시 실행하세요. 이미 만들어진 프레임/클립/나레이션은 건너뜁니다.
특정 샷만 다시 뽑고 싶으면 `output/.../clips/shot_03.mp4` 를 지우고 다시 실행하거나:
```bash
python scripts/generate_clips.py --shotlist shotlist.json \
    --frames-dir output/.../frames --out-dir output/.../clips --only 03
```

### 4. 업로드
기존 파이프라인의 업로더를 그대로 씁니다.
```bash
python ../youtube-automation/scripts/youtube_upload.py \
    --video output/.../final.mp4 --srt output/.../final.srt --title "제목"
```

## 얼굴 컷 (선택)

1. 리뷰어 참조 사진을 `assets/character.png` 에 준비합니다. 본인 사진이 가장 자연스럽고,
   가상 인물이면 무료 이미지 모델(ComfyUI 에서 Flux/Qwen-Image)로 세로 셀카 구도 한 장을 만듭니다.
   **실존 인물의 얼굴은 본인 동의 없이 쓰지 마세요.**
2. 샷리스트에서 얼굴 컷을 `"type": "face", "start_image": "assets/character.png"` 로 지정합니다.
   같은 참조 사진에서 출발하므로 컷 사이에 인물이 유지됩니다.
3. 얼굴 컷은 "말하는 것처럼 보이는" 수준이고 입모양이 대사와 맞지는 않습니다.
   립싱크가 꼭 필요하면 완성된 클립을 오픈소스 립싱크(LatentSync 등)에 한 번 더 통과시키세요.
   AI 생성 인물이 나오는 광고는 플랫폼 정책상 AI 생성물 표시가 필요할 수 있습니다.

## 자주 막히는 곳

| 증상 | 해결 |
|---|---|
| `모델 파일 '...' 이(가) 없습니다` | 파일명이 워크플로우와 정확히 같은지, 폴더가 맞는지 확인. ComfyUI 를 재시작해야 새 파일을 읽습니다. |
| `노드 '...' 가 ComfyUI에 없습니다` | ComfyUI 를 최신으로 업데이트 (Wan 2.2 노드는 2025년 7월 이후 버전) |
| ComfyUI 에서 CUDA out of memory | `--lowvram` 으로 실행, 또는 shotlist 의 `width/height` 를 `480x832` 로 낮추기 |
| 결과가 흐릿하거나 정지 화면 | `steps` 를 30으로, 프롬프트에 동작을 더 구체적으로. 시드를 바꿔 다시 뽑기 |
| 손가락이 이상함 | 부정 프롬프트가 이미 손 관련 항목을 포함합니다. 시드를 바꾸거나 14B 모델로 |
| 한글 자막이 네모로 나옴 | `python scripts/assemble.py ... --font "Malgun Gothic"` 처럼 폰트 이름 지정 |
| edge-tts 오류 | 인터넷 연결 확인. 회사 프록시 환경이면 집에서 시도 |

## 다른 워크플로우 쓰기

ComfyUI 에서 마음에 드는 Wan 워크플로우(LoRA, GGUF 등)를 만들었다면, 설정에서 Dev mode 를 켜고
**Save (API Format)** 으로 내보낸 JSON 을 `workflows/` 에 넣고 shotlist 의 `video.workflow` 에 이름을
적으면 됩니다. 스크립트는 노드 번호가 아니라 종류(LoadImage, CLIPTextEncode, KSampler…)로 찾아서
프롬프트·시드·크기를 채우므로 대부분 그대로 동작합니다.

## 폴더 구조

```
shopping-shorts/
├── main.py                 전체 실행 / --check
├── shotlist.example.json   샷리스트 예시
├── workflows/              ComfyUI API 포맷 워크플로우 (5B, 14B)
├── kaggle/start_comfyui.sh Kaggle 노트북에서 ComfyUI 띄우는 스크립트
├── scripts/
│   ├── write_shotlist.py   샷리스트 요청문 출력 (또는 --auto 로 API 생성)
│   ├── prepare_frames.py   [1] 제품 사진 → 9:16 시작 프레임
│   ├── generate_clips.py   [2] ComfyUI 로 샷별 클립 생성
│   ├── narrate.py          [3] 샷별 edge-tts 나레이션 + 타이밍
│   ├── assemble.py         [4] ffmpeg 합성 (자막, 타이틀, BGM)
│   ├── comfy_client.py     ComfyUI HTTP API
│   └── workflow_patch.py   워크플로우에 값 채우기
└── assets/                 product.png (, character.png)
```
