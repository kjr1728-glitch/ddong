"""파이프라인 공통: 경로, 샷리스트 읽기, ffmpeg 찾기"""
import json
import os
import shutil
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW_DIR = os.path.join(PROJECT_ROOT, "workflows")

# 공식 Wan 2.2 부정 프롬프트 (중국어 원문이 가장 잘 먹힙니다)
DEFAULT_NEGATIVE = (
    "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，"
    "最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，"
    "画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，"
    "杂乱的背景，三条腿，背景人很多，倒着走"
)

# 샷 종류별로 프롬프트 앞에 붙는 공통 지시. 사람 손/얼굴 컷의 사실감을 잡아 줍니다.
TYPE_PREFIX = {
    "product": "Realistic product review video, vertical 9:16 smartphone footage. ",
    "hand": "Realistic UGC product review, vertical 9:16 smartphone footage. Only a real human hand and forearm are visible, natural skin, five fingers, no face. ",
    "face": "Realistic UGC product review, vertical 9:16 selfie-style smartphone footage. The same person as in the image, natural expression, looking at the camera, subtle head movement. ",
}


def load_shotlist(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for key in ("product", "shots"):
        if key not in data:
            raise SystemExit(f"{path}: '{key}' 항목이 없습니다. shotlist.example.json을 참고하세요.")
    if not data["shots"]:
        raise SystemExit(f"{path}: shots 가 비어 있습니다.")
    data.setdefault("video", {})
    data.setdefault("voice", "ko-KR-SunHiNeural")
    base_dir = os.path.dirname(os.path.abspath(path))
    for i, shot in enumerate(data["shots"], start=1):
        shot.setdefault("id", f"{i:02d}")
        shot.setdefault("type", "product")
        shot.setdefault("narration", "")
        if shot["type"] not in TYPE_PREFIX:
            raise SystemExit(f"샷 {shot['id']}: type 은 {list(TYPE_PREFIX)} 중 하나여야 합니다.")
    data["_base_dir"] = base_dir
    return data


def resolve(base_dir: str, path: str) -> str:
    """샷리스트 안의 상대 경로를 샷리스트 파일 기준으로 절대 경로로"""
    if not path:
        return path
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(base_dir, path))


def video_settings(data: dict) -> dict:
    v = dict(data.get("video", {}))
    v.setdefault("workflow", "wan22_5b_i2v")
    v.setdefault("width", 704)
    v.setdefault("height", 1280)
    v.setdefault("length", 121)
    v.setdefault("fps", 24)
    v.setdefault("seed", 0)
    v.setdefault("steps", None)
    return v


def workflow_path(name_or_path: str) -> str:
    if os.path.exists(name_or_path):
        return name_or_path
    candidate = os.path.join(WORKFLOW_DIR, name_or_path + ".json")
    if os.path.exists(candidate):
        return candidate
    raise SystemExit(
        f"워크플로우 '{name_or_path}' 를 찾을 수 없습니다. "
        f"{WORKFLOW_DIR} 안의 파일 이름(확장자 제외) 또는 API 포맷 JSON 경로를 주세요."
    )


def find_ffmpeg() -> str:
    """ffmpeg 실행 파일: 환경변수 → PATH → imageio-ffmpeg 내장 바이너리 순으로 찾는다"""
    env = os.environ.get("FFMPEG_BIN")
    if env and os.path.exists(env):
        return env
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    raise SystemExit(
        "ffmpeg 를 찾을 수 없습니다. 시스템에 설치하거나 (brew/apt/winget) "
        "`pip install imageio-ffmpeg` 로 내장 바이너리를 받으세요."
    )


def media_duration(path: str) -> float:
    """ffprobe 없이도 동작하도록 ffmpeg -i 의 출력에서 길이를 읽는다"""
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        r = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True,
        )
        try:
            return float(r.stdout.strip())
        except ValueError:
            pass
    r = subprocess.run([find_ffmpeg(), "-hide_banner", "-i", path], capture_output=True, text=True)
    import re
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
    if not m:
        raise RuntimeError(f"{path} 의 길이를 읽지 못했습니다:\n{r.stderr[-500:]}")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def run_ffmpeg(args: list, log=print):
    cmd = [find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"] + args
    if log:
        log(f"  ffmpeg → {os.path.basename(args[-1])}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg 실패:\n" + r.stderr[-2000:])
