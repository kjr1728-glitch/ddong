"""ffprobe/ffmpeg 호출 헬퍼. 외부 API 없이 로컬에서만 동작한다."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


class MediaError(RuntimeError):
    pass


def run(cmd: list[str], *, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def probe(path: Path) -> dict:
    """영상 파일의 길이/해상도/fps/오디오 유무를 돌려준다."""
    proc = run([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ])
    if proc.returncode != 0:
        raise MediaError(f"ffprobe 실패 ({path.name}): {proc.stderr.strip()}")

    info = json.loads(proc.stdout)
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if video is None:
        raise MediaError(f"비디오 스트림이 없습니다: {path.name}")

    # r_frame_rate 는 "30/1" 형태의 분수로 온다.
    num, _, den = video.get("r_frame_rate", "30/1").partition("/")
    try:
        fps = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        fps = 30.0

    width = int(video.get("width", 0))
    height = int(video.get("height", 0))

    return {
        "duration": float(info.get("format", {}).get("duration", 0.0)),
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "has_audio": audio is not None,
        "orientation": "portrait" if height > width else "landscape",
        "size_bytes": int(info.get("format", {}).get("size", 0)),
    }


def detect_scene_cuts(path: Path, threshold: float) -> list[float]:
    """장면 전환이 일어난 시각(초) 목록. 전환이 없으면 빈 리스트."""
    proc = run([
        "ffmpeg", "-v", "error", "-i", str(path),
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-fps_mode", "vfr", "-f", "null", "-",
    ])
    # showinfo 는 stderr 로 pts_time 을 뱉는다. 실패해도 빈 목록으로 넘어간다.
    times: list[float] = []
    for line in proc.stderr.splitlines():
        marker = "pts_time:"
        if marker in line:
            tail = line.split(marker, 1)[1].split()[0]
            try:
                times.append(round(float(tail), 3))
            except ValueError:
                continue
    return sorted(set(times))


def extract_thumb(path: Path, at_second: float, dest: Path, width: int = 360) -> bool:
    """지정 시각의 프레임 한 장을 뽑는다. 성공 여부를 돌려준다."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = run([
        "ffmpeg", "-v", "error", "-y",
        "-ss", f"{at_second:.3f}", "-i", str(path),
        "-frames:v", "1", "-vf", f"scale={width}:-2",
        str(dest),
    ])
    return proc.returncode == 0 and dest.exists()


def audio_duration(path: Path) -> float:
    proc = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    if proc.returncode != 0:
        raise MediaError(f"오디오 길이 확인 실패 ({path.name}): {proc.stderr.strip()}")
    return float(proc.stdout.strip())
