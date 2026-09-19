# ComfyUI 포터블 + FLUX Kontext(GGUF Q4) 설치 — RTX 3070 Ti 8GB 기준
# PowerShell에서:  Set-ExecutionPolicy -Scope Process Bypass; .\install_comfyui.ps1
# 설치 위치: D:\ComfyUI (D 드라이브가 없으면 C:\ComfyUI). 총 다운로드 약 12GB, 디스크 20GB 이상 필요.

$ErrorActionPreference = "Stop"
# 이미 설치된 ComfyUI 포터블이 있으면 그 위치를 재사용한다 (중복 설치 방지)
$Existing = @("D:\ComfyUI", "C:\ComfyUI") | Where-Object { Test-Path "$_\ComfyUI_windows_portable\ComfyUI\main.py" } | Select-Object -First 1
$Root = if ($Existing) { $Existing } elseif (Test-Path "D:\") { "D:\ComfyUI" } else { "C:\ComfyUI" }
Write-Host "설치 위치: $Root"
New-Item -ItemType Directory -Force -Path $Root | Out-Null
Set-Location $Root

# $minBytes: 이보다 작으면 오류 페이지·LFS 포인터로 보고 실패 처리 (있던 파일도 다시 받는다)
function Get-File($url, $dst, $minBytes = 100KB) {
  if ((Test-Path $dst) -and (Get-Item $dst).Length -ge $minBytes) { Write-Host "있음: $dst"; return }
  Write-Host "받는 중: $url"
  curl.exe -fL --retry 5 --retry-delay 5 -C - -o "$dst.part" $url
  if ($LASTEXITCODE -ne 0) { throw "다운로드 실패 (curl $LASTEXITCODE): $url" }
  if ((Get-Item "$dst.part").Length -lt $minBytes) { Remove-Item "$dst.part"; throw "받은 파일이 너무 작음 (로그인 제한 또는 LFS 포인터?): $url" }
  Move-Item -Force "$dst.part" $dst
}

# 1) ComfyUI 포터블 (없을 때만 — 압축 해제용 7-Zip도 이때만 설치)
if (-not (Test-Path "$Root\ComfyUI_windows_portable\ComfyUI\main.py")) {
  if (-not (Get-Command 7z -ErrorAction SilentlyContinue) -and -not (Test-Path "C:\Program Files\7-Zip\7z.exe")) {
    Write-Host "7-Zip 설치"
    winget install -e --id 7zip.7zip --accept-source-agreements --accept-package-agreements
  }
  $SevenZip = if (Get-Command 7z -ErrorAction SilentlyContinue) { "7z" } else { "C:\Program Files\7-Zip\7z.exe" }
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
# comfy_pipeline.py는 시스템 python으로 돌리므로 검수용 패키지는 거기에 설치한다
# (ComfyUI 내장 파이썬에 넣으면 numpy 버전이 바뀌어 기존 워크플로가 깨질 수 있음)
if (Get-Command python -ErrorAction SilentlyContinue) {
  python -m pip install -q requests pillow opencv-contrib-python numpy
} else {
  Write-Host "경고: 시스템 python이 없습니다. comfy_pipeline.py 실행 전 python 설치 후 'pip install requests pillow opencv-contrib-python numpy' 필요"
}

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
# black-forest-labs 저장소는 로그인 제한이라 Comfy-Org 재배포본(같은 FLUX VAE, sha256 afc8e282…)을 받는다
Get-File "https://huggingface.co/Comfy-Org/Lumina_Image_2.0_Repackaged/resolve/main/split_files/vae/ae.safetensors" "$Comfy\models\vae\ae.safetensors"
# 리얼리즘 LoRA (MIT, 약 580MB): comfy_pipeline.py가 강도 0.35로 약하게 쓴다 (FLUX 특유의 번들거리는 피부 완화)
New-Item -ItemType Directory -Force -Path "$Comfy\models\loras" | Out-Null
Get-File "https://huggingface.co/strangerzonehf/Flux-Super-Realism-LoRA/resolve/main/super-realism.safetensors" "$Comfy\models\loras\flux-super-realism.safetensors"

# 5) 얼굴 검사용 OpenCV 모델 (자동 검수 루프에서 사용)
New-Item -ItemType Directory -Force -Path "$Root\face_models" | Out-Null
# raw.githubusercontent.com은 LFS 포인터만 주므로 github.com/.../raw/ 경로로 받는다
Get-File "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" "$Root\face_models\yunet.onnx"
Get-File "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx" "$Root\face_models\sface.onnx"

# 6) 실행 배치 (8GB VRAM): 기존 run_nvidia_gpu.bat 실행 줄에 --lowvram --port 8188 만 덧붙인다
$Bat = "$Root\run_comfy_8gb.bat"
$Launch = ".\python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build"
$Stock = "$Root\ComfyUI_windows_portable\run_nvidia_gpu.bat"
if (Test-Path $Stock) {
  $line = Get-Content $Stock | Where-Object { $_ -match "main\.py" } | Select-Object -First 1
  if ($line) { $Launch = $line.Trim() }
}
Set-Content -Path $Bat -Value "@echo off`ncd /d $Root\ComfyUI_windows_portable`n$Launch --lowvram --port 8188`npause" -Encoding ASCII

Write-Host ""
Write-Host "설치 완료. ComfyUI 실행: $Bat"
Write-Host "브라우저에서 http://127.0.0.1:8188 이 열리면 준비된 것입니다."
