"""
파트 렌더: 정지 이미지 장면 + 나레이션 + ASS 자막 → 규격 MP4

    python tools/render_part.py --scenes parts/p1/scenes.json --audio parts/p1/narration.wav \
        --subs parts/p1/subs.ass --out parts/p1/part1.mp4

scenes.json 형식
  [{"image": "scenes/001.png", "start": 0.0, "end": 31.4}, ...]
  - 경로는 scenes.json이 있는 폴더 기준.
  - 마지막 end는 나레이션 길이와 같아야 한다 (자동으로 나레이션 길이에 맞춘다).

규격 반영
  - 이미지는 완전 정지 (규격 3번). 확대·이동 필터를 일절 쓰지 않는다.
  - 16:9가 아닌 이미지는 오류로 멈춘다. 잘라 쓰지 않는다 (규격 8번).
  - 자막 배경 띠: y=830, h=250, 검정 23% (규격 11번).
  - 1920×1080 / 30fps / H.264 / yuv420p / AAC 48kHz 스테레오 / faststart (규격 2번).
  - 첫 8초 안내 문구 없음 (규격 21번).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spec import (AUDIO_BITRATE, AUDIO_CH, AUDIO_RATE, BAND_H, BAND_OPACITY, BAND_W, BAND_X,  # noqa: E402
                  BAND_Y, FONTS_DIR, FPS, HEIGHT, WIDTH)


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if r.returncode != 0:
        raise SystemExit(f"명령 실패:\n{' '.join(map(str, cmd))}\n{r.stderr[-3000:]}")
    return r.stdout


def probe(path, entries):
    return run(["ffprobe", "-v", "error", "-show_entries", entries, "-of", "csv=p=0", str(path)]).strip()


def ff_escape(p: Path) -> str:
    """ffmpeg 필터 인자용 경로 이스케이프 (Windows 드라이브 문자의 ':' 포함)"""
    s = str(p).replace("\\", "/")
    return s.replace(":", r"\:").replace("'", r"\'")


def check_image(path: Path):
    w, h = map(int, probe(path, "stream=width,height").split(",")[:2])
    if abs(w / h - WIDTH / HEIGHT) > 0.01:
        raise SystemExit(f"16:9가 아닌 이미지입니다 ({w}x{h}): {path}\n"
                         "잘라 쓰지 않습니다. 이미지를 16:9로 다시 만들어주세요 (규격 8번).")
    return w, h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenes", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--subs", required=True, help=".ass")
    ap.add_argument("--out", required=True)
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--preset", default="medium")
    a = ap.parse_args()

    scenes_path = Path(a.scenes).resolve()
    base = scenes_path.parent
    scenes = json.loads(scenes_path.read_text(encoding="utf-8"))
    audio = Path(a.audio).resolve()
    subs = Path(a.subs).resolve()
    out = Path(a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    audio_len = float(probe(audio, "format=duration"))
    if not scenes:
        raise SystemExit("scenes.json이 비어 있습니다.")
    scenes = sorted(scenes, key=lambda s: s["start"])
    scenes[-1]["end"] = audio_len  # 마지막 장면을 나레이션 끝까지

    # 장면 연속성 검사
    t = 0.0
    for i, s in enumerate(scenes):
        if abs(s["start"] - t) > 0.01:
            raise SystemExit(f"장면 {i+1} 시작({s['start']})이 이전 장면 끝({t})과 이어지지 않습니다.")
        if s["end"] <= s["start"]:
            raise SystemExit(f"장면 {i+1} 길이가 0 이하입니다.")
        t = s["end"]

    # concat 목록 (정지 이미지 + 길이)
    listfile = out.with_suffix(".scenes.txt")
    with listfile.open("w", encoding="utf-8") as f:
        for s in scenes:
            img = (base / s["image"]).resolve()
            if not img.exists():
                raise SystemExit(f"이미지가 없습니다: {img}")
            check_image(img)
            p = str(img).replace("\\", "/").replace("'", r"'\''")
            f.write(f"file '{p}'\nduration {s['end'] - s['start']:.3f}\n")
        # concat demuxer는 마지막 duration을 무시하므로 마지막 파일을 한 번 더 적는다
        p = str((base / scenes[-1]["image"]).resolve()).replace("\\", "/").replace("'", r"'\''")
        f.write(f"file '{p}'\n")

    band = (f"drawbox=x={BAND_X}:y={BAND_Y}:w={BAND_W}:h={BAND_H}:"
            f"color=black@{BAND_OPACITY}:t=fill")
    vf = (
        f"scale={WIDTH}:{HEIGHT}:flags=lanczos,fps={FPS},format=yuv420p,"
        f"{band},"
        f"ass='{ff_escape(subs)}':fontsdir='{ff_escape(FONTS_DIR)}'"
    )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stats",
        "-f", "concat", "-safe", "0", "-i", str(listfile),
        "-i", str(audio),
        "-vf", vf,
        "-c:v", "libx264", "-preset", a.preset, "-crf", str(a.crf), "-r", str(FPS),
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
        "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", str(AUDIO_RATE), "-ac", str(AUDIO_CH),
        "-t", f"{audio_len:.3f}", "-movflags", "+faststart",
        str(out),
    ]
    print("렌더 중:", out.name, f"({len(scenes)}장면, {audio_len:.1f}초)")
    r = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit("ffmpeg 렌더 실패")
    print("완료:", out)


if __name__ == "__main__":
    main()
