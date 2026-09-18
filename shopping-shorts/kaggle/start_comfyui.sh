#!/bin/bash
# Kaggle 노트북(무료 GPU, 주 30시간)에서 ComfyUI + Wan 2.2 5B 를 띄우고 외부 주소를 만듭니다.
#
# 사용법 (Kaggle 노트북 셀에서):
#   !curl -sL https://raw.githubusercontent.com/kjr1728-glitch/ddong/main/shopping-shorts/kaggle/start_comfyui.sh | bash
#
# 노트북 설정: Settings → Accelerator → GPU T4 x2 (또는 P100), Internet → On
# 마지막에 찍히는 https://xxxx.trycloudflare.com 주소를 내 PC의 .env 에 COMFY_URL 로 넣으면 됩니다.
# 노트북 세션이 끝나면 주소도 사라지니, 다음에 다시 실행하고 새 주소를 넣으세요.
set -e
cd /kaggle/working

if [ ! -d ComfyUI ]; then
  git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git
fi
cd ComfyUI
pip install -q -r requirements.txt huggingface_hub

# Wan 2.2 TI2V 5B (ComfyUI 공식 재패키징, Apache 2.0). 총 약 17GB, 첫 실행에만 받습니다.
python - <<'PY'
from huggingface_hub import hf_hub_download
repo = "Comfy-Org/Wan_2.2_ComfyUI_Repackaged"
files = {
    "split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors": "models/diffusion_models",
    "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors": "models/text_encoders",
    "split_files/vae/wan2.2_vae.safetensors": "models/vae",
}
for f, d in files.items():
    hf_hub_download(repo, f, local_dir=".")
    import os, shutil
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, os.path.basename(f))
    if not os.path.exists(dst):
        shutil.move(f, dst)
    print("ok", dst)
PY

# cloudflared 로 임시 공개 주소 만들기 (가입 불필요)
if [ ! -f /usr/local/bin/cloudflared ]; then
  curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
  chmod +x /usr/local/bin/cloudflared
fi

# T4 는 bf16 을 지원하지 않으므로 fp16 으로 강제, VRAM 16GB 에 맞춰 lowvram
nohup python main.py --listen 0.0.0.0 --port 8188 --fp16-unet --lowvram > comfy.log 2>&1 &
sleep 20
nohup cloudflared tunnel --url http://127.0.0.1:8188 > tunnel.log 2>&1 &
sleep 8

echo "=============================================================="
grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' tunnel.log | head -1 | sed 's/^/COMFY_URL=/'
echo "위 주소를 내 PC 의 shopping-shorts/.env 에 넣으세요."
echo "ComfyUI 로그: tail -f /kaggle/working/ComfyUI/comfy.log"
echo "=============================================================="
