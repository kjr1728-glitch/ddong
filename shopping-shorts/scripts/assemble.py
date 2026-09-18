"""
4단계: ffmpeg 합성 — 클립 + 나레이션 + 자막 → 1080x1920 쇼츠

샷마다:
  - 나레이션이 클립보다 짧으면 클립을 나레이션 길이(+여유)로 자르고
  - 나레이션이 더 길면 클립을 최대 1.6배까지 천천히 재생하고, 그래도 모자라면 마지막 프레임을 유지
  - 나레이션이 없으면 클립 길이 그대로(무음)
그 뒤 순서대로 이어 붙이고, 자막(ASS)과 제품명 타이틀을 태워 넣습니다.

사용법:
    python assemble.py --shotlist shotlist.json --clips-dir output/run/clips \
        --narration-dir output/run/narration --output output/run/final.mp4
"""
import argparse
import glob
import json
import os
import subprocess

from common import find_ffmpeg, load_shotlist, media_duration, run_ffmpeg

TARGET_W, TARGET_H = 1080, 1920
OUT_FPS = 30
MIN_SHOT = 1.5        # 나레이션이 아주 짧아도 이 길이는 보여준다
PAD_AFTER = 0.35      # 나레이션 끝나고 숨 고르는 여유
MAX_SLOW = 1.6        # 클립을 최대 몇 배까지 느리게 늘일지


def find_clip(clips_dir: str, sid: str):
    for ext in (".mp4", ".webm", ".mov", ".webp", ".gif"):
        p = os.path.join(clips_dir, f"shot_{sid}{ext}")
        if os.path.exists(p):
            return p
    return None


def korean_font_family():
    try:
        r = subprocess.run(["fc-match", "-f", "%{family}", ":lang=ko"],
                           capture_output=True, text=True, timeout=10)
        fam = r.stdout.strip().split(",")[0]
        if r.returncode == 0 and fam:
            return fam
    except (OSError, subprocess.SubprocessError):
        pass
    # Windows/Mac 기본 한글 폰트 후보. libass 가 못 찾으면 시스템 기본 폰트로 대체됩니다.
    return "Malgun Gothic"


def ass_time(sec: float) -> str:
    sec = max(0.0, sec)
    cs = int(round(sec * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def srt_time(sec: float) -> str:
    ms = int(round(max(0.0, sec) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def esc_ass(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def write_subtitles(cues: list, title: str, total: float, ass_path: str, srt_path: str, font: str):
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {TARGET_W}
PlayResY: {TARGET_H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},64,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,60,60,300,1
Style: Title,{font},52,&H00FFFFFF,&H000000FF,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,3,10,0,8,80,80,180,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    if title:
        lines.append(f"Dialogue: 0,{ass_time(0)},{ass_time(total)},Title,,0,0,0,,{esc_ass(title)}")
    for start, end, text in cues:
        lines.append(f"Dialogue: 1,{ass_time(start)},{ass_time(end)},Caption,,0,0,0,,{esc_ass(text)}")
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    srt = []
    for i, (start, end, text) in enumerate(cues, start=1):
        srt += [str(i), f"{srt_time(start)} --> {srt_time(end)}", text, ""]
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt))


def build_segment(clip: str, narration, target: float, clip_len: float, dest: str, log):
    """한 샷을 1080x1920, 30fps, 오디오 포함 세그먼트로 렌더링"""
    slow = 1.0
    if target > clip_len + 0.05:
        slow = min(target / clip_len, MAX_SLOW)
    vf = (
        f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,"
        f"crop={TARGET_W}:{TARGET_H},setsar=1,"
        f"setpts={slow:.4f}*PTS,fps={OUT_FPS},"
        f"tpad=stop_mode=clone:stop_duration={max(0.0, target - clip_len * slow) + 1.0:.3f},"
        f"trim=duration={target:.3f},setpts=PTS-STARTPTS,format=yuv420p"
    )
    args = ["-i", clip]
    if narration:
        args += ["-i", narration]
        af = f"apad,atrim=duration={target:.3f},asetpts=PTS-STARTPTS"
        args += ["-filter_complex", f"[0:v]{vf}[v];[1:a]{af}[a]", "-map", "[v]", "-map", "[a]"]
    else:
        args += ["-f", "lavfi", "-t", f"{target:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
        args += ["-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]", "-map", "1:a"]
    args += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-r", str(OUT_FPS),
             "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", "-shortest", dest]
    run_ffmpeg(args, log=log)


def assemble(shotlist_path: str, clips_dir: str, narration_dir: str, output: str,
             bgm: str = None, bgm_volume: float = 0.12, no_captions: bool = False,
             font: str = None, log=print) -> str:
    data = load_shotlist(shotlist_path)
    title = data["product"].get("tagline") or data["product"].get("name", "")
    work = os.path.join(os.path.dirname(os.path.abspath(output)), "segments")
    os.makedirs(work, exist_ok=True)

    segments, cues, t = [], [], 0.0
    for shot in data["shots"]:
        sid = shot["id"]
        clip = find_clip(clips_dir, sid)
        if not clip:
            raise SystemExit(f"샷 {sid} 클립이 없습니다 ({clips_dir}). generate_clips.py 를 먼저 실행하세요.")
        clip_len = media_duration(clip)
        nar = os.path.join(narration_dir, f"shot_{sid}.mp3") if narration_dir else None
        meta = os.path.join(narration_dir, f"shot_{sid}.json") if narration_dir else None
        if nar and os.path.exists(nar) and os.path.exists(meta):
            nar_len = media_duration(nar)
            target = max(MIN_SHOT, nar_len + PAD_AFTER)
            # 클립을 최대로 늘여도 모자라면 마지막 프레임을 잡아 둡니다.
            with open(meta, "r", encoding="utf-8") as f:
                for c in json.load(f)["cues"]:
                    cues.append((t + c["start"], t + min(c["end"], target), c["text"]))
        else:
            nar, target = None, clip_len
        seg = os.path.join(work, f"seg_{sid}.mp4")
        log(f"[샷 {sid}] 클립 {clip_len:.2f}s → {target:.2f}s" + (" (나레이션)" if nar else " (무음)"))
        build_segment(clip, nar, target, clip_len, seg, log)
        segments.append(seg)
        t += target

    concat_list = os.path.join(work, "concat.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        for s in segments:
            f.write(f"file '{os.path.abspath(s)}'\n")
    joined = os.path.join(work, "joined.mp4")
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", joined], log=log)

    base = os.path.splitext(output)[0]
    ass_path, srt_path = base + ".ass", base + ".srt"
    write_subtitles(cues, title, t, ass_path, srt_path, font or korean_font_family())

    args = ["-i", joined]
    filters = []
    if not no_captions:
        # libass 필터 경로: 윈도우 드라이브 콜론과 특수문자 이스케이프
        ass_arg = os.path.abspath(ass_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        filters.append(f"subtitles='{ass_arg}'")
    vf = ",".join(filters) if filters else "null"
    if bgm and os.path.exists(bgm):
        args += ["-stream_loop", "-1", "-i", bgm]
        args += ["-filter_complex",
                 f"[0:v]{vf}[v];[1:a]volume={bgm_volume}[b];[0:a][b]amix=inputs=2:duration=first:dropout_transition=2[a]",
                 "-map", "[v]", "-map", "[a]"]
    else:
        args += ["-vf", vf, "-map", "0:v", "-map", "0:a"]
    args += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "160k",
             "-movflags", "+faststart", output]
    run_ffmpeg(args, log=log)
    log(f"\n완성: {output} ({t:.1f}초)\n자막: {srt_path}")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shotlist", required=True)
    parser.add_argument("--clips-dir", required=True)
    parser.add_argument("--narration-dir", default=None)
    parser.add_argument("--output", required=True)
    parser.add_argument("--bgm", default=None, help="배경음악 파일 (선택)")
    parser.add_argument("--bgm-volume", type=float, default=0.12)
    parser.add_argument("--no-captions", action="store_true")
    parser.add_argument("--font", default=None, help="자막 폰트 이름 (기본: 시스템 한글 폰트 자동)")
    args = parser.parse_args()
    find_ffmpeg()
    assemble(args.shotlist, args.clips_dir, args.narration_dir, args.output,
             bgm=args.bgm, bgm_volume=args.bgm_volume, no_captions=args.no_captions, font=args.font)


if __name__ == "__main__":
    main()
