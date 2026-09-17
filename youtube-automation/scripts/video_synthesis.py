"""
영상 합성 — moviepy 2.x (완전 무료, 오픈소스)

나레이션에 맞춰 배경 영상을 붙이고 자막을 입힙니다. 자동 생성 영상이 죽어 보이는
가장 큰 이유가 "한 장면이 통째로 오래 재생되는 것"과 "화면이 말하는 내용과
무관한 것"이라, 이 두 가지를 다음 방식으로 처리합니다.

- 스크립트의 [SECTION: ... | keywords] 구간마다 그 키워드로 받은 영상만 씁니다.
- 한 컷을 몇 초 단위로 끊고, 같은 영상이라도 매번 다른 구간을 잘라 씁니다.
- 컷 사이를 부드럽게 겹쳐 넘깁니다.
- 각 컷에 아주 느린 확대를 넣어 화면이 멈춰 있지 않게 합니다.
- assets/music 폴더에 음악이 있으면 작은 소리로 깔아줍니다.

사용법:
    python video_synthesis.py --narration output/narration.mp3 \
        --broll-dir assets/broll --script output/script.txt
"""
import argparse
import glob
import os
import re
import subprocess

from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    afx,
    concatenate_videoclips,
    vfx,
)

TARGET_SIZE = (1920, 1080)  # 가로 롱폼 기준. 쇼츠는 (1080, 1920)으로 바꾸세요.

DEFAULT_CUT_SECONDS = 4.0   # 한 컷의 길이. 짧을수록 빠르고 답답하지 않게 느껴집니다.
CROSSFADE = 0.4             # 컷과 컷이 겹쳐 넘어가는 시간
ZOOM_PER_CUT = 0.06         # 컷마다 6%씩 아주 천천히 확대
MUSIC_VOLUME = 0.10         # 나레이션을 덮지 않을 정도의 배경음악 크기
MUSIC_FADEOUT = 3.0

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUSIC_DIR = os.path.join(PROJECT_ROOT, "assets", "music")
MUSIC_EXTS = ("*.mp3", "*.m4a", "*.wav", "*.ogg")

SECTION_PATTERN = re.compile(r"\[SECTION:\s*(.*?)\s*\]")

KOREAN_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\malgunbd.ttf",   # 맑은 고딕 굵게 — 자막은 굵은 쪽이 잘 읽힙니다
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\gulim.ttc",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/Library/Fonts/AppleGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
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


def keyword_slug(keyword: str) -> str:
    """broll_fetcher.py가 파일 이름을 만들 때 쓰는 규칙과 똑같이 맞춰야 합니다."""
    return re.sub(r"[^\w]+", "_", keyword).strip("_") or "broll"


def parse_sections(script_path: str):
    """
    스크립트를 [SECTION: 한글 | english] 단위로 쪼갠다.
    돌려주는 값: [(키워드, 본문), ...] — 태그가 없으면 전체를 한 덩어리로 본다.
    """
    with open(script_path, "r", encoding="utf-8") as f:
        raw = f.read()

    matches = list(SECTION_PATTERN.finditer(raw))
    if not matches:
        return [(None, raw.strip())]

    sections = []
    for i, m in enumerate(matches):
        tag = m.group(1)
        keyword = tag.split("|")[-1].strip() if "|" in tag else None
        if keyword and re.search(r"[가-힣]", keyword):
            keyword = None  # 한글 키워드로는 스톡 영상을 못 찾습니다
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        body = raw[m.end():end].strip()
        if body:
            sections.append((keyword, body))

    return sections or [(None, raw.strip())]


def clips_for_keyword(broll_dir: str, keyword, all_paths: list):
    """해당 구간의 키워드로 받은 영상만 고른다. 없으면 전체에서 쓴다."""
    if keyword:
        matched = sorted(glob.glob(os.path.join(broll_dir, f"{keyword_slug(keyword)}_*.mp4")))
        if matched:
            return matched
    return all_paths


def fit_to_frame(clip):
    """비율을 유지한 채 프레임을 채우고 넘치는 부분만 잘라낸다"""
    target_w, target_h = TARGET_SIZE
    scale = max(target_w / clip.w, target_h / clip.h)
    resized = clip.resized(scale)
    return resized.cropped(
        x_center=resized.w / 2, y_center=resized.h / 2,
        width=target_w, height=target_h,
    )


def add_slow_zoom(clip):
    """아주 느린 확대. 정지 화면처럼 보이는 걸 막아줍니다."""
    duration = clip.duration
    zoomed = clip.resized(lambda t: 1 + ZOOM_PER_CUT * (t / duration))
    return CompositeVideoClip(
        [zoomed.with_position("center")], size=TARGET_SIZE
    ).with_duration(duration)


def make_cut(path: str, start: float, length: float, zoom: bool):
    """영상 하나에서 start 지점부터 length 만큼 잘라 한 컷을 만든다"""
    source = VideoFileClip(path)
    if not source.duration or source.duration <= 0:
        source.close()
        return None

    length = min(length, source.duration)
    start = start % max(source.duration - length, 0.01) if source.duration > length else 0.0

    cut = fit_to_frame(source.subclipped(start, start + length)).without_audio()
    return add_slow_zoom(cut) if zoom else cut


def build_video(script_path: str, broll_dir: str, duration: float, cut_seconds: float, zoom: bool):
    """구간별로 관련 영상을 짧게 끊어 이어 붙인다"""
    all_paths = sorted(glob.glob(os.path.join(broll_dir, "*.mp4")))
    if not all_paths:
        raise SystemExit(f"{broll_dir}에 b-roll 영상이 없습니다. broll_fetcher.py를 먼저 실행하세요.")

    sections = parse_sections(script_path)

    # 구간 길이는 글자 수 비율로 나눕니다. 나레이션 속도가 거의 일정해서 잘 맞습니다.
    weights = [max(len(re.sub(r"\s+", "", body)), 1) for _, body in sections]
    total_weight = sum(weights)

    cuts = []
    for (keyword, _), weight in zip(sections, weights):
        span = duration * weight / total_weight
        paths = clips_for_keyword(broll_dir, keyword, all_paths)

        filled = 0.0
        index = 0
        while filled < span - 0.05:
            # 컷을 겹쳐 넘기기 때문에 두 번째 컷부터는 겹치는 만큼 전체 길이가
            # 줄어듭니다. 그만큼 더 길게 잘라야 목표 길이를 채웁니다.
            overlap = CROSSFADE if cuts else 0.0
            length = min(cut_seconds, span - filled + overlap)
            if length - overlap < 1.0 and cuts:
                break
            path = paths[index % len(paths)]
            # 같은 영상을 다시 쓸 때는 다른 구간이 나오도록 시작 지점을 밀어줍니다
            offset = (index // len(paths) + 1) * cut_seconds
            try:
                cut = make_cut(path, offset, length, zoom)
            except Exception as e:
                print(f"[경고] 열 수 없는 b-roll 건너뜀: {os.path.basename(path)} ({e})")
                cut = None
            index += 1
            if cut is None:
                if index > len(paths) * 3:
                    break
                continue
            cuts.append(cut)
            filled += cut.duration - overlap

    if not cuts:
        raise SystemExit("사용할 수 있는 b-roll 영상이 하나도 없습니다.")

    print(f"컷 {len(cuts)}개로 구성 (구간 {len(sections)}개, 컷당 약 {cut_seconds:.0f}초)")

    # 컷 사이를 부드럽게 겹쳐 넘깁니다
    faded = [cuts[0]] + [c.with_effects([vfx.CrossFadeIn(CROSSFADE)]) for c in cuts[1:]]
    video = concatenate_videoclips(faded, method="compose", padding=-CROSSFADE)

    if video.duration < duration:
        video = video.with_effects([vfx.Loop(duration=duration)])
    return video.subclipped(0, duration)


def parse_srt(path: str):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    def to_seconds(stamp: str) -> float:
        hours, minutes, rest = stamp.split(":")
        secs, _, millis = rest.replace(".", ",").partition(",")
        return int(hours) * 3600 + int(minutes) * 60 + int(secs) + int(millis or 0) / 1000

    cues = []
    for block in re.split(r"\n\s*\n", content):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if len(lines) < 3:
            continue
        match = re.search(r"([\d:,.]+)\s*-->\s*([\d:,.]+)", lines[1])
        if not match:
            continue
        cues.append((to_seconds(match.group(1)), to_seconds(match.group(2)), " ".join(lines[2:])))
    return cues


def even_split_cues(script_path: str, total_duration: float):
    with open(script_path, "r", encoding="utf-8") as f:
        raw = f.read()

    text = SECTION_PATTERN.sub("", raw).strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?？！])\s+", text) if s.strip()]
    if not sentences:
        return []

    per = total_duration / len(sentences)
    return [(i * per, (i + 1) * per, s) for i, s in enumerate(sentences)]


def build_caption_clips(cues: list, font: str):
    if not cues:
        return []

    if not font:
        print(
            "[경고] 한글 폰트를 찾지 못해 자막을 넣지 않습니다.\n"
            "       --font 로 폰트 파일 경로를 직접 지정할 수 있습니다."
        )
        return []

    clips = []
    for start, end, text in cues:
        length = max(end - start, 0.3)
        try:
            clip = (
                TextClip(
                    font=font,
                    text=text,
                    font_size=62,
                    color="white",
                    stroke_color="black",
                    stroke_width=5,
                    method="caption",
                    size=(TARGET_SIZE[0] - 260, None),
                    text_align="center",
                )
                .with_position(("center", TARGET_SIZE[1] - 300))
                .with_start(start)
                .with_duration(length)
                .with_effects([vfx.CrossFadeIn(0.15)])
            )
        except Exception as e:
            print(f"[경고] 자막을 만들 수 없어 영상만 렌더링합니다 ({e}).")
            return []
        clips.append(clip)

    return clips


def find_music(explicit: str):
    if explicit:
        if not os.path.exists(explicit):
            raise SystemExit(f"음악 파일이 없습니다: {explicit}")
        return explicit

    for pattern in MUSIC_EXTS:
        found = sorted(glob.glob(os.path.join(MUSIC_DIR, pattern)))
        if found:
            return found[0]
    return None


def mix_audio(narration, music_path: str, duration: float):
    """나레이션 위에 배경음악을 작게 깐다"""
    music = AudioFileClip(music_path).with_effects(
        [
            afx.AudioLoop(duration=duration),
            afx.MultiplyVolume(MUSIC_VOLUME),
            afx.AudioFadeOut(min(MUSIC_FADEOUT, duration / 2)),
        ]
    )
    print(f"배경음악: {os.path.basename(music_path)} (소리 크기 {int(MUSIC_VOLUME * 100)}%)")
    return CompositeAudioClip([narration, music])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--narration", required=True)
    parser.add_argument("--broll-dir", default="assets/broll")
    parser.add_argument("--script", required=True)
    parser.add_argument("--output", default="output/final_video.mp4")
    parser.add_argument("--srt", default=None, help="자막 파일 (기본값: 나레이션과 같은 이름의 .srt)")
    parser.add_argument("--no-captions", action="store_true", help="자막 없이 렌더링")
    parser.add_argument("--font", default=None, help="자막 폰트 파일 (미지정 시 자동 탐색)")
    parser.add_argument(
        "--cut-seconds", type=float, default=DEFAULT_CUT_SECONDS,
        help=f"한 컷의 길이(초). 기본 {DEFAULT_CUT_SECONDS:.0f}초, 짧을수록 빠른 느낌",
    )
    parser.add_argument("--no-zoom", action="store_true", help="느린 확대 효과 끄기 (렌더링이 빨라짐)")
    parser.add_argument("--music", default=None, help="배경음악 파일 (기본: assets/music 폴더에서 자동)")
    parser.add_argument("--no-music", action="store_true", help="배경음악 넣지 않기")
    args = parser.parse_args()

    print("나레이션 오디오 로딩 중...")
    narration = AudioFileClip(args.narration)
    duration = narration.duration

    print(f"영상 길이: {duration:.1f}초 — 배경 영상 구성 중...")
    video = build_video(args.script, args.broll_dir, duration, args.cut_seconds, not args.no_zoom)

    audio = narration
    if not args.no_music:
        music_path = find_music(args.music)
        if music_path:
            audio = mix_audio(narration, music_path, duration)
        else:
            print(f"배경음악 없음 — 넣으려면 {MUSIC_DIR} 폴더에 음악 파일을 두세요.")
    video = video.with_audio(audio)

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
            print(f"자막 폰트: {font}")
        caption_clips = build_caption_clips(cues, font)

    final = CompositeVideoClip([video] + caption_clips) if caption_clips else video

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    print(f"렌더링 중... → {args.output}")
    # 임시 음성 파일을 결과물 옆에 만들게 합니다. 지정하지 않으면 명령을 실행한
    # 폴더에 찌꺼기 파일을 남깁니다.
    temp_audio = os.path.splitext(args.output)[0] + ".temp-audio.m4a"
    try:
        final.write_videofile(
            args.output, fps=30, codec="libx264", audio_codec="aac", threads=4,
            temp_audiofile=temp_audio, remove_temp=True,
        )
    finally:
        final.close()
        narration.close()

    print(f"완료: {args.output}")


if __name__ == "__main__":
    main()
