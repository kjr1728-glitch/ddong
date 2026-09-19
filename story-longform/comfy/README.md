# ComfyUI 무료 이미지 자동화 (RTX 3070 Ti 8GB)

대본·나레이션·자막·렌더·검수는 클라우드 Claude Code가 하고, **이미지 생성만** 이 PC에서 돌립니다.
모델은 FLUX.1 Kontext dev의 4비트 양자화(GGUF Q4_K_S)라 8GB VRAM에 들어갑니다.
기준 얼굴 한 장을 참조로 넣어 장면을 만들기 때문에 같은 인물이 유지됩니다.

## 1. 설치 (한 번만, 약 30~60분, 다운로드 약 12GB)

PowerShell을 **관리자 권한**으로 열고:
```
cd ddong\story-longform\comfy
Set-ExecutionPolicy -Scope Process Bypass
.\install_comfyui.ps1
```
이미 ComfyUI 포터블이 있으면(`D:\ComfyUI` 또는 `C:\ComfyUI`) 그 위치를 재사용해 모델·노드만 추가합니다.
없으면 D 드라이브가 있을 때 `D:\ComfyUI`, 없을 때 `C:\ComfyUI`에 새로 설치됩니다.
끝나면 설치 위치에 `run_comfy_8gb.bat`가 생깁니다. (이 PC: `C:\ComfyUI\run_comfy_8gb.bat`, Wan 2.2와 공용)

## 2. ComfyUI 켜기
`run_comfy_8gb.bat` 실행 → 검은 창에 `To see the GUI go to: http://127.0.0.1:8188` 가 뜨면 준비 완료.
이 창은 이미지 생성 동안 계속 켜 둡니다.

## 3. 인물 기준 얼굴 만들기
새 명령창(cmd)에서:
```
cd ddong\story-longform
python comfy\comfy_pipeline.py refs --prompts "works\2026-09-팔순잔치\characters\prompts.json" --out "works\2026-09-팔순잔치\characters"
```
`characters\ref_서윤.png` 등 6장이 생깁니다. 열어 보고 마음에 안 드는 인물은 그 파일만 지우고 같은 명령을 다시 실행하면 그 인물만 다시 만듭니다.
- 후보를 여러 장 뽑아 고르려면 `--n 3` (→ `characters\_candidates\이름_1.png …`), 특정 인물만은 `--only 서윤,윤재국`.
- 스타일은 사용자 승인 견본(드라마 캐스팅 프로필: 밝은 회색 배경, 부드러운 정면 조명, 저대비)에 맞춰져 있습니다.
  기본값 `--guidance 2.3 --lora flux-super-realism.safetensors --lora-strength 0.35`. LoRA를 0.9로 올리면 주름·그림자가 과해져 반려된 적이 있습니다.
- 손목 흉터·손 자세 문구는 기준 얼굴에서 자동으로 빠집니다(장면 프롬프트가 담당).
6장이 확정되면 이 6장을 Claude Code 대화창에 올려 승인을 받습니다 (규격 5번: 작품 시작 시 기준 얼굴 확정).

## 4. 장면 생성 + 자동 검수
```
python comfy\comfy_pipeline.py scenes --prompts "works\2026-09-팔순잔치\parts\p1\scene_prompts.json" --refs "works\2026-09-팔순잔치\characters" --out "works\2026-09-팔순잔치\parts\p1\scenes"
```
- 장면마다 생성 → 얼굴 개수·동일 인물 유사도·눈·잘림을 자동 검사 → 불합격이면 시드를 바꿔 재생성(기본 4회).
- 통과한 것만 `scenes\001.png … 020.png`로 저장. 모든 시도는 `scenes\_tries\`에 남고 점수는 `scenes\qc_images.json`에 기록.
- 1장에 약 40~90초. 20장면이면 재생성 포함 30~60분.
- 특정 장면만 다시: `--only 3,7,12`

## 5. 클라우드로 보내기
`scenes\001.png ~ 020.png`와 `qc_images.json`을 Claude Code 대화창에 올립니다.
Claude Code가 한 장씩 열어 눈·손·손가락·표정을 2차 검사하고, 불합격 번호를 알려주면 `--only`로 그 장면만 다시 만듭니다.
통과하면 렌더·검수·MP4 전달은 클라우드에서 합니다.

## 문제가 생기면
- `ComfyUI 거부: ... UnetLoaderGGUF` → GGUF 커스텀 노드가 안 깔림. ComfyUI 창을 껐다 켜거나 설치 스크립트 재실행.
- 메모리 부족(CUDA out of memory) → `run_comfy_8gb.bat`의 `--lowvram`을 `--novram`으로 바꿔 실행.
- 얼굴 불일치가 계속 나오는 인물 → 기준 얼굴을 정면에 가깝고 조명이 고른 것으로 다시 만든다.
- 두 명 장면에서 얼굴이 섞임 → 그 장면만 프롬프트에 "left person / right person" 위치를 명시해 재시도.
