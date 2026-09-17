"""
직접 찍은 영상으로 쇼핑 쇼츠 만들기

잘 되는 쇼핑 쇼츠는 사람이 실제로 물건을 쓰는 장면을 보여줍니다. 그 장면은
사람이 찍어야 합니다. 이 도구는 찍어온 영상을 받아 나머지를 자동으로 합니다.

- 영상을 0.6~0.9초짜리 짧은 컷으로 쪼개 빠르게 이어 붙입니다
- 나레이션을 만들고, 말에 맞춰 자막을 띄웁니다
- 자막은 반투명 둥근 박스에 흰 글씨로, 화면 위에서 5분의 1 지점에 놓습니다
- 컷이 바뀔 때 효과음을 넣고 배경음악을 깝니다

준비물
1. assets/my_footage/<상품이름>/ 폴더에 찍은 영상 파일들
2. 같은 폴더에 script.txt — 한 줄에 한 문장씩 (자막이자 나레이션이 됩니다)

사용법:
    python scripts/footage_shorts.py --footage-dir assets/my_footage/선풍기 \
        --output output/shorts/fan.mp4
"""
import argparse
import glob
import os
import random
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    afx,
    concatenate_videoclips,
    vfx,
)

SHORTS_SIZE = (1080, 1920)

# 참고 영상을 재보니 컷 하나가 평균 0.6초였습니다. 그 리듬을 기본으로 씁니다.
CUT_MIN = 0.6
CUT_MAX = 0.9
CROSSFADE = 0.12          # 짧게 겹쳐 딱딱 끊기는 느낌을 살립니다

CAPTION_Y_RATIO = 0.19    # 화면 위에서 19% 지점 (참고 영상과 같은 자리)
CAPTION_FONT_SIZE = 52
CAPTION_BOX_ALPHA = 150   # 반투명 정도
CAPTION_BOX_COLOR = (30, 30, 30)
CAPTION_PAD_X, CAPTION_PAD_Y = 26, 16
CAPTION_RADIUS = 14

MUSIC_VOLUME = 0.08
SFX_VOLUME = 0.3

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUSIC_DIR = os.path.join(PROJECT_ROOT, "assets", "music")
SFX_DIR = os.path.join(PROJECT_ROOT, "assets", "sfx")

VIDEO_EXTS = ("*.mp4", "*.mov", "*.MP4", "*.MOV", "*.m4v", "*.avi")

KOREAN_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\malgunbd.ttf",
    r"C:\Windows\Fonts\malgun.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]


def find_korean_font():
    for path in KOREAN_FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{file}", ":lang=ko"],
            capture_output=True, text=True, timeout=10,
        )
        path = result.stdout.strip()
        if result.returncode == 0 and path and os.path.exists(path):
            return path
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def fit_to_frame(clip):
    """세로 화면을 비율 유지한 채 채우고 넘치는 부분을 자른다"""
    target_w, target_h = SHORTS_SIZE
    scale = max(target_w / clip.w, target_h / clip.h)
    resized = clip.resized(scale)
    return resized.cropped(
        x_center=resized.w / 2, y_center=resized.h / 2,
        width=target_w, height=target_h,
    )


def make_caption_image(text: str, font_path: str) -> np.ndarray:
    """
    반투명 둥근 박스에 흰 글씨를 얹은 자막 이미지를 만든다.
    moviepy의 글자 기능으로는 둥근 배경을 못 만들어서 직접 그립니다.
    """
    font = ImageFont.truetype(font_path, CAPTION_FONT_SIZE)

    # 화면 폭을 넘지 않게 줄바꿈합니다
    max_text_w = SHORTS_SIZE[0] - 120 - CAPTION_PAD_X * 2
    words = text.split()
    lines, current = [], ""
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for word in words:
        candidate = f"{current} {word}".strip()
        if probe.textlength(candidate, font=font) <= max_text_w or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if not lines:
        lines = [text]

    line_h = CAPTION_FONT_SIZE + 12
    text_w = int(max(probe.textlength(line, font=font) for line in lines))
    box_w = text_w + CAPTION_PAD_X * 2
    box_h = line_h * len(lines) + CAPTION_PAD_Y * 2

    canvas = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        [0, 0, box_w - 1, box_h - 1],
        radius=CAPTION_RADIUS,
        fill=CAPTION_BOX_COLOR + (CAPTION_BOX_ALPHA,),
    )
    for i, line in enumerate(lines):
        line_w = probe.textlength(line, font=font)
        draw.text(
            ((box_w - line_w) / 2, CAPTION_PAD_Y + i * line_h),
            line, font=font, fill=(255, 255, 255, 255),
        )

    return np.array(canvas)


def load_cuts(footage_dir: str, total_duration: float, cut_min: float, cut_max: float):
    """찍어온 영상들을 짧은 컷으로 쪼개 필요한 길이만큼 모은다"""
    paths = []
    for pattern in VIDEO_EXTS:
        paths.extend(glob.glob(os.path.join(footage_dir, pattern)))
    paths = sorted(set(paths))

    if not paths:
        raise SystemExit(
            f"{footage_dir} 폴더에 영상 파일이 없습니다.\n"
            "폰으로 찍은 영상을 이 폴더에 넣어주세요 (mp4, mov 등)."
        )

    sources = []
    for path in paths:
        try:
            clip = VideoFileClip(path)
            if clip.duration and clip.duration > 0.5:
                sources.append(clip)
            else:
                clip.close()
        except Exception as e:
            print(f"[경고] 열 수 없는 영상 건너뜀: {os.path.basename(path)} ({e})")

    if not sources:
        raise SystemExit("사용할 수 있는 영상이 하나도 없습니다.")

    print(f"영상 {len(sources)}개에서 컷을 뽑습니다 (총 {sum(s.duration for s in sources):.1f}초 분량)")

    cuts = []
    filled = 0.0
    # 각 영상에서 어디까지 썼는지 기억해 같은 장면이 반복되지 않게 합니다
    positions = [0.0] * len(sources)
    index = 0
    guard = 0

    while filled < total_duration and guard < 2000:
        guard += 1
        source = sources[index % len(sources)]
        start = positions[index % len(sources)]
        length = random.uniform(cut_min, cut_max)

        if start + length > source.duration:
            positions[index % len(sources)] = 0.0
            start = 0.0
            if length > source.duration:
                length = source.duration

        overlap = CROSSFADE if cuts else 0.0
        remaining = total_duration - filled + overlap
        length = min(length, remaining)
        if length < 0.25:
            break

        cut = fit_to_frame(source.subclipped(start, start + length)).without_audio()
        cuts.append(cut)
        positions[index % len(sources)] = start + length
        filled += cut.duration - overlap
        index += 1

    if not cuts:
        raise SystemExit("컷을 하나도 만들지 못했습니다. 영상 길이를 확인하세요.")

    print(f"컷 {len(cuts)}개 (평균 {sum(c.duration for c in cuts)/len(cuts):.2f}초)")
    return cuts


def caption_clips_from_srt(srt_path: str, font_path: str):
    """나레이션 자막 파일을 읽어 둥근 박스 자막으로 만든다"""
    import re

    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    def to_seconds(stamp):
        h, m, rest = stamp.split(":")
        s, _, ms = rest.replace(".", ",").partition(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms or 0) / 1000

    clips = []
    y = int(SHORTS_SIZE[1] * CAPTION_Y_RATIO)

    for block in re.split(r"\n\s*\n", content):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if len(lines) < 3:
            continue
        match = re.search(r"([\d:,.]+)\s*-->\s*([\d:,.]+)", lines[1])
        if not match:
            continue
        start, end = to_seconds(match.group(1)), to_seconds(match.group(2))
        text = " ".join(lines[2:])
        if end <= start:
            continue

        image = make_caption_image(text, font_path)
        clips.append(
            ImageClip(image, transparent=True)
            .with_start(start)
            .with_duration(end - start)
            .with_position(("center", y))
        )

    return clips


def find_audio(directory: str, exts=("*.mp3", "*.m4a", "*.wav", "*.ogg")):
    for pattern in exts:
        found = sorted(glob.glob(os.path.join(directory, pattern)))
        if found:
            return found[0]
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--footage-dir", required=True, help="찍은 영상이 들어 있는 폴더")
    parser.add_argument("--narration", default=None, help="나레이션 mp3 (없으면 script.txt로 만듭니다)")
    parser.add_argument("--srt", default=None, help="자막 파일 (기본: 나레이션과 같은 이름의 .srt)")
    parser.add_argument("--output", required=True)
    parser.add_argument("--cut-min", type=float, default=CUT_MIN)
    parser.add_argument("--cut-max", type=float, default=CUT_MAX)
    parser.add_argument("--font", default=None)
    parser.add_argument("--music", default=None)
    parser.add_argument("--no-music", action="store_true")
    parser.add_argument("--no-sfx", action="store_true")
    parser.add_argument("--duration", type=float, default=None,
                        help="영상 길이(초). 생략하면 나레이션 길이에 맞춥니다")
    args = parser.parse_args()

    font_path = args.font or find_korean_font()
    if not font_path:
        raise SystemExit("한글 폰트를 찾지 못했습니다. --font로 폰트 파일을 지정해주세요.")

    narration_path = args.narration
    if not narration_path:
        guess = os.path.join(args.footage_dir, "narration.mp3")
        narration_path = guess if os.path.exists(guess) else None

    if narration_path and os.path.exists(narration_path):
        narration = AudioFileClip(narration_path)
        duration = args.duration or narration.duration
        print(f"나레이션: {os.path.basename(narration_path)} ({narration.duration:.1f}초)")
    else:
        narration = None
        duration = args.duration or 25.0
        print(f"나레이션 없음 — {duration:.0f}초로 만듭니다.")
        print("  목소리를 넣으려면 먼저 narration.py로 mp3를 만드세요.")

    cuts = load_cuts(args.footage_dir, duration, args.cut_min, args.cut_max)

    faded = [cuts[0]] + [c.with_effects([vfx.CrossFadeIn(CROSSFADE)]) for c in cuts[1:]]
    video = concatenate_videoclips(faded, method="compose", padding=-CROSSFADE)
    if video.duration > duration:
        video = video.subclipped(0, duration)

    # 자막
    layers = [video]
    srt_path = args.srt
    if not srt_path and narration_path:
        candidate = os.path.splitext(narration_path)[0] + ".srt"
        srt_path = candidate if os.path.exists(candidate) else None

    if srt_path and os.path.exists(srt_path):
        caption_clips = caption_clips_from_srt(srt_path, font_path)
        layers.extend(caption_clips)
        print(f"자막 {len(caption_clips)}개 ({os.path.basename(srt_path)})")
    else:
        print("자막 없음 — 나레이션을 만들면 .srt가 함께 생겨 자막이 붙습니다.")

    # 소리
    tracks = []
    if narration:
        tracks.append(narration)

    if not args.no_sfx:
        sfx_path = find_audio(SFX_DIR)
        if sfx_path:
            elapsed = 0.0
            hits = 0
            for cut in cuts[:-1]:
                elapsed += cut.duration - CROSSFADE
                if 0 < elapsed < video.duration and hits < 40:
                    tracks.append(
                        AudioFileClip(sfx_path)
                        .with_effects([afx.MultiplyVolume(SFX_VOLUME)])
                        .with_start(elapsed)
                    )
                    hits += 1
            if hits:
                print(f"전환 효과음 {hits}번")

    if not args.no_music:
        music_path = args.music or find_audio(MUSIC_DIR)
        if music_path:
            tracks.append(
                AudioFileClip(music_path).with_effects(
                    [
                        afx.AudioLoop(duration=video.duration),
                        afx.MultiplyVolume(MUSIC_VOLUME),
                        afx.AudioFadeOut(min(2.0, video.duration / 2)),
                    ]
                )
            )
            print(f"배경음악: {os.path.basename(music_path)}")

    final = CompositeVideoClip(layers, size=SHORTS_SIZE) if len(layers) > 1 else video
    if tracks:
        final = final.with_audio(
            CompositeAudioClip(tracks) if len(tracks) > 1 else tracks[0]
        )

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    print(f"렌더링 중 ({final.duration:.1f}초)... → {args.output}")
    temp_audio = os.path.splitext(args.output)[0] + ".temp-audio.m4a"
    try:
        final.write_videofile(
            args.output, fps=30, codec="libx264", audio_codec="aac", threads=4,
            temp_audiofile=temp_audio, remove_temp=True,
        )
    finally:
        final.close()

    print(f"완료: {args.output}")


if __name__ == "__main__":
    main()
