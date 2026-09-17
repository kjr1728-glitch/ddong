"""
영상 합성 — ffmpeg 기반 moviepy 사용 (완전 무료, 오픈소스)
나레이션 오디오 길이에 맞춰 b-roll 클립들을 이어 붙이고 자막을 입힙니다.

자막은 narration.py가 만든 .srt(실제 발화 타이밍)를 우선 사용하고,
없으면 문장 균등 분할로 대체합니다.

사용법:
    python video_synthesis.py --narration output/narration.mp3 \
        --broll-dir assets/broll --script output/script.txt
"""
import argparse
import glob
import os
import re
import subprocess

from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
    vfx,
)

TARGET_SIZE = (1920, 1080)  # 가로 롱폼 기준. 쇼츠는 (1080, 1920)으로 바꾸세요.


def find_korean_font():
    """한글이 깨지지 않는 폰트를 시스템에서 찾는다 (없으면 None)"""
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{file}", ":lang=ko"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        path = result.stdout.strip()
        if result.returncode == 0 and path and os.path.exists(path):
            return path
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def fit_to_frame(clip):
    """
    화면 비율을 유지한 채 프레임을 꽉 채우고 넘치는 부분만 잘라낸다.
    그냥 TARGET_SIZE로 늘이면 4:3 소스가 옆으로 찌그러져 보입니다.
    """
    target_w, target_h = TARGET_SIZE
    scale = max(target_w / clip.w, target_h / clip.h)
    resized = clip.resize(scale)
    return resized.crop(
        x_center=resized.w / 2,
        y_center=resized.h / 2,
        width=target_w,
        height=target_h,
    )


def load_broll_clips(broll_dir: str, target_duration: float):
    """b-roll 영상들을 모아 target_duration 길이가 될 때까지 반복/자르기"""
    paths = sorted(glob.glob(os.path.join(broll_dir, "*.mp4")))
    if not paths:
        raise SystemExit(f"{broll_dir}에 b-roll 영상이 없습니다. broll_fetcher.py를 먼저 실행하세요.")

    clips = []
    total = 0.0
    i = 0
    # 같은 파일을 계속 돌려써야 할 수도 있으므로 반복 횟수에 상한을 둔다
    max_clips = max(len(paths) * 50, 200)

    while total < target_duration and len(clips) < max_clips:
        path = paths[i % len(paths)]
        i += 1
        try:
            clip = fit_to_frame(VideoFileClip(path))
        except Exception as e:
            print(f"[경고] 열 수 없는 b-roll 건너뜀: {path} ({e})")
            if i >= len(paths) and not clips:
                raise SystemExit("사용할 수 있는 b-roll 영상이 하나도 없습니다.")
            continue

        if not clip.duration or clip.duration <= 0:
            print(f"[경고] 길이가 0인 b-roll 건너뜀: {path}")
            clip.close()
            continue

        clips.append(clip.without_audio())
        total += clip.duration

    if not clips:
        raise SystemExit("사용할 수 있는 b-roll 영상이 하나도 없습니다.")

    if total < target_duration:
        print(
            f"[경고] b-roll 총 길이({total:.1f}초)가 나레이션({target_duration:.1f}초)보다 짧습니다.\n"
            "       영상이 나레이션보다 먼저 끝나지 않도록 마지막 장면을 늘립니다."
        )
        joined = concatenate_videoclips(clips, method="compose")
        return joined.fx(vfx.loop, duration=target_duration)

    return concatenate_videoclips(clips, method="compose").subclip(0, target_duration)


def parse_srt(path: str):
    """narration.py가 만든 자막 파일을 (시작, 끝, 텍스트) 목록으로 읽는다"""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    def to_seconds(stamp: str) -> float:
        hours, minutes, rest = stamp.split(":")
        secs, millis = rest.replace(".", ",").split(",")
        return int(hours) * 3600 + int(minutes) * 60 + int(secs) + int(millis) / 1000

    cues = []
    for block in re.split(r"\n\s*\n", content):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if len(lines) < 3:
            continue
        match = re.search(r"([\d:,.]+)\s*-->\s*([\d:,.]+)", lines[1])
        if not match:
            continue
        cues.append(
            (to_seconds(match.group(1)), to_seconds(match.group(2)), " ".join(lines[2:]))
        )
    return cues


def even_split_cues(script_path: str, total_duration: float):
    """자막 파일이 없을 때 쓰는 대체 방식 — 문장 수로 균등 분할"""
    with open(script_path, "r", encoding="utf-8") as f:
        raw = f.read()

    text = re.sub(r"\[SECTION:.*?\]", "", raw).strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?？！])\s+", text) if s.strip()]
    if not sentences:
        return []

    per = total_duration / len(sentences)
    return [(i * per, (i + 1) * per, s) for i, s in enumerate(sentences)]


def build_caption_clips(cues: list, font: str = None):
    """자막 클립 생성. ImageMagick이 없으면 빈 목록을 돌려주고 계속 진행한다"""
    if not cues:
        return []

    kwargs = dict(
        fontsize=48,
        color="white",
        stroke_color="black",
        stroke_width=2,
        method="caption",
        size=(TARGET_SIZE[0] - 120, None),
    )
    if font:
        kwargs["font"] = font

    clips = []
    for start, end, text in cues:
        duration = max(end - start, 0.3)
        try:
            clip = (
                TextClip(text, **kwargs)
                .set_position(("center", TARGET_SIZE[1] - 260))
                .set_start(start)
                .set_duration(duration)
            )
        except Exception as e:
            print(
                f"[경고] 자막을 만들 수 없습니다 ({e}).\n"
                "       moviepy의 TextClip은 ImageMagick이 필요합니다.\n"
                "       Mac: brew install imagemagick / Ubuntu: sudo apt install imagemagick\n"
                "       자막 없이 영상만 렌더링합니다. (.srt 파일은 그대로 남으니\n"
                "       유튜브 업로드 시 자막 파일로 따로 올려도 됩니다.)"
            )
            return []
        clips.append(clip)

    return clips


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--narration", required=True)
    parser.add_argument("--broll-dir", default="assets/broll")
    parser.add_argument("--script", required=True)
    parser.add_argument("--output", default="output/final_video.mp4")
    parser.add_argument(
        "--srt",
        default=None,
        help="자막 파일 (기본값: 나레이션과 같은 이름의 .srt, 없으면 균등 분할)",
    )
    parser.add_argument("--no-captions", action="store_true", help="자막 없이 렌더링")
    parser.add_argument("--font", default=None, help="자막 폰트 (미지정 시 한글 폰트 자동 탐색)")
    args = parser.parse_args()

    print("나레이션 오디오 로딩 중...")
    audio = AudioFileClip(args.narration)
    duration = audio.duration

    print(f"영상 길이: {duration:.1f}초 — b-roll 합성 중...")
    video = load_broll_clips(args.broll_dir, duration).set_audio(audio)

    caption_clips = []
    if not args.no_captions:
        srt_path = args.srt or os.path.splitext(args.narration)[0] + ".srt"
        if os.path.exists(srt_path):
            cues = parse_srt(srt_path)
            print(f"자막: {srt_path} 사용 ({len(cues)}개 구간, 발화 타이밍 기준)")
        else:
            cues = even_split_cues(args.script, duration)
            print(f"자막: .srt가 없어 문장 균등 분할로 대체 ({len(cues)}개 구간)")

        font = args.font or find_korean_font()
        if not args.font and font:
            print(f"자막 폰트 자동 선택: {font}")
        caption_clips = build_caption_clips(cues, font)

    final = CompositeVideoClip([video] + caption_clips) if caption_clips else video

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    print(f"렌더링 중... → {args.output}")
    try:
        final.write_videofile(
            args.output,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            threads=4,
        )
    finally:
        final.close()
        audio.close()

    print(f"완료: {args.output}")


if __name__ == "__main__":
    main()
