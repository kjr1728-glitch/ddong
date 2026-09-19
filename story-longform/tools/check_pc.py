"""
집 PC 점검: 그래픽카드, ComfyUI 설치 위치, 모델·커스텀 노드 유무를 한 번에 출력

    python tools/check_pc.py

출력을 그대로 Claude Code에 붙여넣으면 ComfyUI 설치/보강 스크립트를 맞춰 만들 수 있다.
아무것도 바꾸지 않고 읽기만 한다.
"""
import os
import shutil
import subprocess
from pathlib import Path


def sh(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20, shell=isinstance(cmd, str)).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"(실행 실패: {e})"


def section(title):
    print(f"\n== {title} ==")


section("그래픽카드")
if shutil.which("nvidia-smi"):
    print(sh(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"]))
else:
    print("nvidia-smi 없음 → NVIDIA 드라이버가 없거나 NVIDIA 카드가 아님")
    if os.name == "nt":
        print(sh('wmic path win32_VideoController get name,AdapterRAM /format:list'))

section("Python / ffmpeg")
print("python:", sh(["python", "--version"]) or sh(["python3", "--version"]))
print("ffmpeg:", (sh(["ffmpeg", "-version"]).splitlines() or ["없음"])[0])

section("ComfyUI 설치 후보")
home = Path.home()
roots = [home, home / "Desktop", home / "Documents", home / "Downloads", Path("C:/"), Path("D:/"), Path("E:/"),
         home / "AppData/Local/Programs", home / "pinokio/api", home / "StabilityMatrix"]
names = ["ComfyUI", "ComfyUI_windows_portable", "comfyui", "ComfyUI-master"]
found = []
for r in roots:
    if not r.exists():
        continue
    try:
        for child in r.iterdir():
            if child.is_dir() and (child.name in names or child.name.lower().startswith("comfyui")):
                found.append(child)
                inner = child / "ComfyUI"
                if inner.is_dir():
                    found.append(inner)
    except PermissionError:
        pass
found = [p for p in found if (p / "main.py").exists() or (p / "run_nvidia_gpu.bat").exists()]
if not found:
    print("ComfyUI 폴더를 못 찾음 (main.py 또는 run_nvidia_gpu.bat 기준). 설치 위치를 직접 알려주세요.")
for p in dict.fromkeys(found):
    print("발견:", p)
    base = p if (p / "main.py").exists() else p / "ComfyUI"
    for sub in ["models/unet", "models/diffusion_models", "models/checkpoints", "models/clip", "models/vae",
                "models/pulid", "models/insightface", "models/loras"]:
        d = base / sub
        if d.exists():
            files = [f.name for f in d.iterdir() if f.is_file() and f.suffix in (".safetensors", ".gguf", ".ckpt", ".pt", ".bin", ".onnx")]
            print(f"  {sub}: {len(files)}개", files[:8])
    cn = base / "custom_nodes"
    if cn.exists():
        nodes = sorted(d.name for d in cn.iterdir() if d.is_dir() and not d.name.startswith("__"))
        print(f"  custom_nodes: {len(nodes)}개", nodes[:20])
    py = p / "python_embeded/python.exe"
    if py.exists():
        print("  포터블 파이썬:", py)
        print("  torch:", sh([str(py), "-c", "import torch;print(torch.__version__, torch.cuda.is_available())"]))

section("디스크 여유")
for drive in ["C:/", "D:/"] if os.name == "nt" else ["/"]:
    if Path(drive).exists():
        u = shutil.disk_usage(drive)
        print(f"{drive} 여유 {u.free / 2**30:.0f} GB / 전체 {u.total / 2**30:.0f} GB")
