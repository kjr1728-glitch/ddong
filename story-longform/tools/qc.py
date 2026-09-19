"""
검수 (규격 24·25번): 렌더된 영상을 실제로 검사하고, 검사한 범위만 보고한다.

    python tools/qc.py --video parts/p1/part1.mp4 [--subs parts/p1/subs.ass] [--scenes parts/p1/scenes.json]

검사 항목
  1. 규격: 1920×1080, 30fps, H.264, yuv420p, AAC 48kHz 스테레오, faststart
  2. 전체 디코딩 (깨진 프레임·오류)
  3. 검은 화면 구간
  4. 프레임 수 = 길이 × 30 (프레임 누락)
  5. 영상/음성 길이 차이 (싱크)
  6. 정지 검사: 장면 첫/끝 프레임 SSIM 비교 (확대·이동이 있으면 값이 떨어진다)
  7. 자막: 겹침, 화면 밖 시간, 첫/마지막/가장 긴 자막 시각, 스타일 줄이 규격과 같은지
  8. 장면 전환 시각이 scenes.json과 맞는지

이 도구는 "얼굴·눈·손 오류"와 "실제 청취"는 검사하지 못한다. 그 항목은 사람이 또는
이미지를 직접 열어 보는 방식으로 따로 한다. 보고서에도 그렇게 적는다.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spec import ASS_STYLE_LINE, FPS, HEIGHT, WIDTH  # noqa: E402

FAIL = []
WARN = []
OK = []


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def probe_json(path):
    r = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    return json.loads(r.stdout)


def check_format(video):
    info = probe_json(video)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    fps = eval(v["r_frame_rate"])  # "30/1"
    items = [
        ("해상도", f"{v['width']}x{v['height']}", v["width"] == WIDTH and v["height"] == HEIGHT),
        ("fps", f"{fps:g}", abs(fps - FPS) < 0.01),
        ("영상 코덱", v["codec_name"], v["codec_name"] == "h264"),
        ("픽셀 포맷", v["pix_fmt"], v["pix_fmt"] == "yuv420p"),
        ("오디오", "없음" if a is None else f"{a['codec_name']} {a['sample_rate']}Hz {a['channels']}ch",
         a is not None and a["codec_name"] == "aac" and a["sample_rate"] == "48000" and a["channels"] == 2),
    ]
    for name, val, ok in items:
        (OK if ok else FAIL).append(f"{name}: {val}")
    # faststart: moov가 mdat보다 앞에 있는지
    head = Path(video).read_bytes()[:1 << 20]
    mi, di = head.find(b"moov"), head.find(b"mdat")
    (OK if (mi != -1 and (di == -1 or mi < di)) else FAIL).append("faststart(moov 앞쪽 배치)")
    dur_v = float(v.get("duration") or info["format"]["duration"])
    dur_a = float(a["duration"]) if a and a.get("duration") else dur_v
    diff = abs(dur_v - dur_a)
    (OK if diff < 0.1 else FAIL).append(f"영상/음성 길이 차이 {diff:.3f}s (영상 {dur_v:.2f}s)")
    return dur_v, int(v.get("nb_frames") or 0)


def check_decode_black_frames(video, duration, nb_frames):
    """전체 디코딩 + 검은 화면 + 프레임 수를 한 번에"""
    r = run(["ffmpeg", "-v", "info", "-i", str(video),
             "-vf", "blackdetect=d=0.3:pic_th=0.98", "-an", "-f", "null", "-"])
    log = r.stderr
    errors = [l for l in log.splitlines() if "error" in l.lower() and "blackdetect" not in l]
    (OK if not errors else FAIL).append(f"전체 디코딩 (오류 {len(errors)}건)")
    blacks = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", log)
    (OK if not blacks else FAIL).append(
        "검은 화면 " + ("없음" if not blacks else ", ".join(f"{s}~{e}s" for s, e in blacks)))
    m = re.findall(r"frame=\s*(\d+)", log)
    decoded = int(m[-1]) if m else 0
    expected = round(duration * FPS)
    (OK if abs(decoded - expected) <= 2 else FAIL).append(
        f"프레임 수 {decoded} (기대 {expected}, 길이 {duration:.2f}s×{FPS})")
    return decoded


def detect_cuts(video):
    r = run(["ffmpeg", "-v", "info", "-i", str(video),
             "-vf", "select='gt(scene,0.3)',showinfo", "-an", "-f", "null", "-"])
    return [float(t) for t in re.findall(r"pts_time:([\d.]+)", r.stderr)]


def ssim_between(video, t1, t2, tmpdir):
    """두 시각의 프레임을 자막 띠 위쪽(0~830px)만 잘라 SSIM 비교"""
    a, b = tmpdir / "qc_a.png", tmpdir / "qc_b.png"
    for t, f in ((t1, a), (t2, b)):
        run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video),
             "-frames:v", "1", "-vf", "crop=1920:830:0:0", "-y", str(f)])
    r = run(["ffmpeg", "-v", "info", "-i", str(a), "-i", str(b), "-lavfi", "ssim", "-f", "null", "-"])
    m = re.search(r"All:([\d.]+)", r.stderr)
    for f in (a, b):
        f.unlink(missing_ok=True)
    return float(m.group(1)) if m else None


def check_static_and_cuts(video, scenes, duration):
    """장면 전환 시각 확인 + 장면 안 정지 여부(첫/끝 프레임 SSIM)"""
    cuts = detect_cuts(video)
    OK.append(f"장면 전환 감지 {len(cuts)}회")
    if scenes:
        expected = [s["start"] for s in scenes[1:]]
        missed = [e for e in expected if not any(abs(e - c) < 0.2 for c in cuts)]
        (OK if not missed else WARN).append(
            f"scenes.json 전환 {len(expected)}회 중 미감지 {len(missed)}회"
            + ("" if not missed else f": {', '.join(f'{m:.1f}s' for m in missed)} (두 이미지가 매우 비슷할 때도 생김)"))
        spans = [(s["start"], s["end"]) for s in scenes]
    else:
        edges = [0.0] + cuts + [duration]
        spans = list(zip(edges, edges[1:]))
    # 정지 검사: 장면 첫/끝 프레임 SSIM. 정지 이미지는 0.97 이상, 느린 확대·이동은 0.9 아래로 떨어진다.
    tmpdir = Path(video).resolve().parent
    moving = []
    for i, (s, e) in enumerate(spans, 1):
        if e - s < 1.0:
            continue
        v = ssim_between(video, s + 0.2, e - 0.2, tmpdir)
        if v is not None and v < 0.93:
            moving.append(f"장면 {i} ({s:.1f}~{e:.1f}s) SSIM {v:.3f}")
    (OK if not moving else FAIL).append(
        f"정지 이미지 검사 (장면 {len(spans)}개 첫/끝 프레임 비교): 움직임 " + ("없음" if not moving else ", ".join(moving)))


def parse_ass(path):
    cues = []
    style_ok = False
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("Style: Default,"):
            style_ok = line.strip() == ASS_STYLE_LINE
        if line.startswith("Dialogue:"):
            f = line.split(",", 9)
            cues.append((to_sec(f[1]), to_sec(f[2]), f[9]))
    return style_ok, cues


def to_sec(t):
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def check_subs(subs, duration):
    style_ok, cues = parse_ass(subs)
    (OK if style_ok else FAIL).append("ASS 스타일 줄이 규격과 동일")
    overlaps = [(a, b) for a, b in zip(cues, cues[1:]) if b[0] < a[1] - 1e-3]
    (OK if not overlaps else FAIL).append(f"자막 겹침 {len(overlaps)}건")
    out_of_range = [c for c in cues if c[1] > duration + 0.05]
    (OK if not out_of_range else FAIL).append(f"영상 길이를 넘는 자막 {len(out_of_range)}건")
    too_long = [c for c in cues if any(len(l) > 26 for l in c[2].split(r"\N")) or c[2].count(r"\N") > 1]
    (OK if not too_long else FAIL).append(f"26자 초과 줄 또는 3줄 이상 자막 {len(too_long)}건")
    if cues:
        longest = max(cues, key=lambda c: len(c[2]))
        OK.append(f"첫 자막 {cues[0][0]:.2f}~{cues[0][1]:.2f}s: {cues[0][2]}")
        OK.append(f"마지막 자막 {cues[-1][0]:.2f}~{cues[-1][1]:.2f}s: {cues[-1][2]}")
        OK.append(f"가장 긴 자막 {longest[0]:.2f}~{longest[1]:.2f}s: {longest[2]}")
        gap_end = duration - cues[-1][1]
        (OK if gap_end < 3.0 else WARN).append(f"마지막 자막 뒤 여백 {gap_end:.2f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--subs")
    ap.add_argument("--scenes")
    ap.add_argument("--report", help="결과를 저장할 .md 경로")
    a = ap.parse_args()

    video = Path(a.video)
    duration, nb = check_format(video)
    check_decode_black_frames(video, duration, nb)
    scenes = json.loads(Path(a.scenes).read_text(encoding="utf-8")) if a.scenes else None
    check_static_and_cuts(video, scenes, duration)
    if a.subs:
        check_subs(a.subs, duration)

    lines = [f"# 검수 결과: {video.name}", ""]
    lines += ["## 통과"] + [f"- {x}" for x in OK] + [""]
    if WARN:
        lines += ["## 확인 필요"] + [f"- {x}" for x in WARN] + [""]
    lines += ["## 불합격"] + ([f"- {x}" for x in FAIL] if FAIL else ["- 없음"]) + [""]
    lines += ["## 이 도구가 검사하지 않은 것",
              "- 얼굴·눈·손 오류, 인물 일관성 (이미지를 직접 열어 확인)",
              "- 발음·음질의 실제 청취 (음성 인식 대조와 파형 검사는 별도, 최종 청취는 사람이)",
              "- 자막 오탈자와 줄바꿈의 의미 적절성 (대본 대조는 사람이)"]
    report = "\n".join(lines)
    print(report)
    if a.report:
        Path(a.report).write_text(report, encoding="utf-8")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
