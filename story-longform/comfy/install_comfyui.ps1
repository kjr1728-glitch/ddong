# ComfyUI 포터블 + FLUX Kontext(GGUF Q4) 설치 — RTX 3070 Ti 8GB 기준
# PowerShell에서:  Set-ExecutionPolicy -Scope Process Bypass; .\install_comfyui.ps1
# 설치 위치: D:\ComfyUI (D 드라이브가 없으면 C:\ComfyUI). 총 다운로드 약 12GB, 디스크 20GB 이상 필요.

$ErrorActionPreference = "Stop"
$Root = if (Test-Path "D:\") { "D:\ComfyUI" } else { "C:\ComfyUI" }
New-Item -ItemType Directory -Force -Path $Root | Out-Null
Set-Location $Root

function Get-File($url, $dst) {
  if (Test-Path $dst) { Write-Host "있음: $dst"; return }
  Write-Host "받는 중: $url"
  curl.exe -L --retry 5 --retry-delay 5 -C - -o "$dst.part" $url
  Move-Item -Force "$dst.part" $dst
}

# 1) 7-Zip (포터블 압축 해제용)
if (-not (Get-Command 7z -ErrorAction SilentlyContinue) -and -not (Test-Path "C:\Program Files\7-Zip\7z.exe")) {
  Write-Host "7-Zip 설치"
  winget install -e --id 7zip.7zip --accept-source-agreements --accept-package-agreements
}
$SevenZip = if (Get-Command 7z -ErrorAction SilentlyContinue) { "7z" } else { "C:\Program Files\7-Zip\7z.exe" }

# 2) ComfyUI 포터블
if (-not (Test-Path "$Root\ComfyUI_windows_portable\ComfyUI\main.py")) {
  Get-File "https://github.com/comfyanonymous/ComfyUI/releases/latest/download/ComfyUI_windows_portable_nvidia.7z" "$Root\comfyui_portable.7z"
  & $SevenZip x "$Root\comfyui_portable.7z" -o"$Root" -y | Out-Null
}
$Comfy = "$Root\ComfyUI_windows_portable\ComfyUI"
$Py = "$Root\ComfyUI_windows_portable\python_embeded\python.exe"

# 3) 커스텀 노드: GGUF 로더, Manager
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { winget install -e --id Git.Git --accept-source-agreements --accept-package-agreements }
if (-not (Test-Path "$Comfy\custom_nodes\ComfyUI-GGUF")) { git clone https://github.com/city96/ComfyUI-GGUF "$Comfy\custom_nodes\ComfyUI-GGUF" }
if (-not (Test-Path "$Comfy\custom_nodes\ComfyUI-Manager")) { git clone https://github.com/ltdrdata/ComfyUI-Manager "$Comfy\custom_nodes\ComfyUI-Manager" }
& $Py -m pip install -q -r "$Comfy\custom_nodes\ComfyUI-GGUF\requirements.txt"
& $Py -m pip install -q requests pillow opencv-contrib-python numpy

# 4) 모델 (Hugging Face에서 파일명을 API로 조회해 Q4_K_S를 고른다)
function Get-HFFile($repo, $pattern, $dst) {
  if (Test-Path $dst) { Write-Host "있음: $dst"; return }
  $info = Invoke-RestMethod "https://huggingface.co/api/models/$repo"
  $name = ($info.siblings | ForEach-Object { $_.rfilename } | Where-Object { $_ -match $pattern } | Select-Object -First 1)
  if (-not $name) { throw "파일을 못 찾음: $repo / $pattern" }
  Get-File "https://huggingface.co/$repo/resolve/main/$name" $dst
}
New-Item -ItemType Directory -Force -Path "$Comfy\models\unet", "$Comfy\models\clip", "$Comfy\models\vae" | Out-Null
Get-HFFile "QuantStack/FLUX.1-Kontext-dev-GGUF" "Q4_K_S\.gguf$" "$Comfy\models\unet\flux1-kontext-dev-Q4_K_S.gguf"
Get-File "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors" "$Comfy\models\clip\t5xxl_fp8_e4m3fn.safetensors"
Get-File "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors" "$Comfy\models\clip\clip_l.safetensors"
Get-File "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors" "$Comfy\models\vae\ae.safetensors"

# 5) 얼굴 검사용 OpenCV 모델 (자동 검수 루프에서 사용)
New-Item -ItemType Directory -Force -Path "$Root\face_models" | Out-Null
Get-File "https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" "$Root\face_models\yunet.onnx"
Get-File "https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx" "$Root\face_models\sface.onnx"

# 6) 실행 배치 (8GB VRAM: --lowvram)
$Bat = "$Root\run_comfy_8gb.bat"
Set-Content -Path $Bat -Value "@echo off`ncd /d $Root\ComfyUI_windows_portable`n.\python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build --lowvram --listen 127.0.0.1 --port 8188`npause" -Encoding ASCII

Write-Host ""
Write-Host "설치 완료. ComfyUI 실행: $Bat"
Write-Host "브라우저에서 http://127.0.0.1:8188 이 열리면 준비된 것입니다."
