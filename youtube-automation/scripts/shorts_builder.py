"""
쇼핑 쇼츠 만들기 (세로 1080x1920)

상품 한 개당 이미지가 한 장뿐이라, 한 장으로 화면을 채우면서도 지루하지 않게
만드는 것이 관건입니다. 그래서 이렇게 구성합니다.

- 배경: 같은 상품 이미지를 크게 확대하고 흐리게 깔아 세로 화면을 채웁니다.
  검은 여백을 남기는 것보다 훨씬 완성돼 보입니다.
- 상품: 가운데에 선명하게 얹고 아주 느리게 확대합니다.
- 맨 위: 1~2초 안에 읽히는 훅 문구를 크게 넣습니다.
- 아래: 상품 이름과 가격을 넣습니다.
- 한 영상에 상품 여러 개를 넣습니다. 한 개만 계속 보여주면 금방 나가버립니다.
- 마지막: 링크 안내와 수수료 고지 문구를 넣습니다.

수수료 고지는 법에서 요구하는 사항이라 끄는 옵션을 두지 않았습니다.

사용법:
    python scripts/shorts_builder.py --products output/products.json --start 0 --count 3
"""
import argparse
import glob
import io
import json
import math
import os
import re
import struct
import subprocess
import wave

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter
from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    afx,
    concatenate_videoclips,
    vfx,
)

SHORTS_SIZE = (1080, 1920)
# 화면을 위에서 아래로 나눠 씁니다. 겹치면 글자가 뭉개지므로 자리를 못 박아둡니다.
HOOK_Y = 150            # 맨 위 훅 문구
PRODUCT_AREA = (400, 1230)   # 상품 카드
CAPTION_Y = 1270        # 말에 맞춘 자막 (또는 상품 이름)
CAPTION_H = 200
PRICE_Y = 1520          # 가격
ROCKET_Y = 1680         # 로켓배송 표시
SECONDS_PER_PRODUCT = 5.0
OUTRO_SECONDS = 3.0
CROSSFADE = 0.25          # 짧을수록 화면이 팍팍 넘어갑니다
PUNCH_ZOOM = 0.12         # 장면이 바뀌는 순간 살짝 들어갔다 나오는 정도
WORD_POP_SCALE = 1.18     # 단어가 튀어나올 때 커지는 정도
WORDS_PER_LINE = 3        # 한 번에 띄울 단어 수
SFX_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "sfx")

MUSIC_VOLUME = 0.10
MUSIC_FADEOUT = 2.0

# 공정거래위원회가 요구하는 대가성 표시입니다. 영상 안과 설명란 양쪽에 들어갑니다.
DISCLOSURE = "이 영상은 쿠팡 파트너스 활동의 일환으로 수수료를 제공받습니다"

# 1~2초 안에 읽히는 짧은 훅. 상품마다 돌려 씁니다.
HOOKS = [
    "이거 왜 이제 알았지?",
    "이 가격이 말이 되나",
    "한 번 쓰면 못 돌아감",
    "이거 하나면 끝남",
    "사고 나서 후회 안 한 것",
    "이런 게 있었네",
]

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUSIC_DIR = os.path.join(PROJECT_ROOT, "assets", "music")
MUSIC_EXTS = ("*.mp3", "*.m4a", "*.wav", "*.ogg")

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


def fetch_image(url: str, cache_dir: str):
    """
    상품 이미지를 PIL 이미지로 돌려준다. 받은 건 다시 안 받게 저장해둔다.
    인터넷 주소뿐 아니라 내 컴퓨터에 있는 파일 경로도 그대로 받습니다.
    (상품을 직접 골라 이미지를 준비하는 경우에 씁니다.)
    """
    if not url.startswith(("http://", "https://")):
        local = url[7:] if url.startswith("file://") else url
        if not os.path.exists(local):
            raise FileNotFoundError(f"이미지 파일이 없습니다: {local}")
        return Image.open(local).convert("RGB")

    os.makedirs(cache_dir, exist_ok=True)
    name = re.sub(r"[^\w.]+", "_", url.split("/")[-1])[:80] or "image.jpg"
    path = os.path.join(cache_dir, name)

    if not os.path.exists(path) or os.path.getsize(path) == 0:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        with open(path, "wb") as f:
            f.write(resp.content)

    with open(path, "rb") as f:
        return Image.open(io.BytesIO(f.read())).convert("RGB")


def compose_frame(image: Image.Image) -> np.ndarray:
    """
    세로 화면 한 장을 만든다.

    배경은 같은 이미지를 꽉 채워 자른 뒤 흐리게 깔고, 그 위에 상품을 흰 카드에
    올려 얹는다. 쿠팡 상품 이미지는 대부분 흰 배경이라 그냥 붙이면 흰 네모가
    화면을 눌러버린다. 모서리를 둥글린 카드로 올리면 그게 덜하다.

    글자 자리(위쪽 훅, 아래쪽 이름과 가격)는 비워두고 상품을 가운데에 놓는다.
    """
    target_w, target_h = SHORTS_SIZE

    # 배경: 비율 유지하며 화면을 덮도록 키우고 가운데를 자른 다음 흐리게
    scale = max(target_w / image.width, target_h / image.height)
    bg = image.resize((int(image.width * scale) + 1, int(image.height * scale) + 1), Image.LANCZOS)
    left = (bg.width - target_w) // 2
    top = (bg.height - target_h) // 2
    bg = bg.crop((left, top, left + target_w, top + target_h))
    bg = bg.filter(ImageFilter.GaussianBlur(32))
    bg = Image.blend(bg, Image.new("RGB", bg.size, (0, 0, 0)), 0.5)

    # 상품 카드가 놓일 자리. 위는 훅 문구, 아래는 이름과 가격에 내어줍니다.
    area_top, area_bottom = PRODUCT_AREA
    area_h = area_bottom - area_top
    max_w = int(target_w * 0.78)

    fit = min(max_w / image.width, area_h / image.height)
    product_w = max(int(image.width * fit), 1)
    product_h = max(int(image.height * fit), 1)
    product = image.resize((product_w, product_h), Image.LANCZOS)

    # 흰 카드에 얹고 모서리를 둥글립니다
    pad = 26
    card_w, card_h = product_w + pad * 2, product_h + pad * 2
    card = Image.new("RGB", (card_w, card_h), (255, 255, 255))
    card.paste(product, (pad, pad))
    mask = Image.new("L", (card_w, card_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, card_w - 1, card_h - 1], radius=40, fill=255)

    card_x = (target_w - card_w) // 2
    card_y = area_top + (area_h - card_h) // 2
    bg.paste(card, (card_x, card_y), mask)

    # 아래쪽 글자가 잘 읽히도록 어두운 그라데이션을 깝니다
    band_h = 640
    band = Image.new("RGB", (target_w, band_h), (0, 0, 0))
    band_mask = Image.new("L", (target_w, band_h))
    for y in range(band_h):
        band_mask.paste(int(200 * (y / band_h) ** 1.4), (0, y, target_w, y + 1))
    bg.paste(band, (0, target_h - band_h), band_mask)

    return np.array(bg)


def text_clip(text: str, font: str, size: int, y: int, duration: float, color="white", stroke=6):
    return (
        TextClip(
            font=font, text=text, font_size=size, color=color,
            stroke_color="black", stroke_width=stroke,
            method="caption", size=(SHORTS_SIZE[0] - 120, None), text_align="center",
        )
        .with_position(("center", y))
        .with_duration(duration)
    )


def make_whoosh(path: str, duration: float = 0.28, sample_rate: int = 44100):
    """
    장면 전환용 효과음을 직접 만들어 저장한다.
    받아올 파일이 없어도 되도록 간단한 바람소리를 합성합니다.
    (assets/sfx 폴더에 직접 넣은 파일이 있으면 그걸 먼저 씁니다.)
    """
    frames = int(sample_rate * duration)
    data = bytearray()
    state = 0.0
    for i in range(frames):
        t = i / frames
        # 잡음을 저역 통과시켜 '쉭' 하는 소리를 만들고, 앞뒤를 부드럽게 줄입니다
        noise = math.sin(i * 12.9898) * 43758.5453
        noise -= math.floor(noise)
        noise = noise * 2 - 1
        cutoff = 0.06 + 0.5 * t
        state += cutoff * (noise - state)
        envelope = math.sin(math.pi * t) ** 1.6
        value = int(max(-1.0, min(1.0, state * envelope * 1.6)) * 22000)
        data += struct.pack("<h", value)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(bytes(data))
    return path


def find_sfx() -> str:
    """전환 효과음을 찾는다. 없으면 직접 만들어 쓴다."""
    for pattern in ("*.wav", "*.mp3", "*.m4a"):
        found = sorted(glob.glob(os.path.join(SFX_DIR, pattern)))
        if found:
            return found[0]
    generated = os.path.join(SFX_DIR, "_whoosh.wav")
    if not os.path.exists(generated):
        make_whoosh(generated)
    return generated


def load_word_timings(narration_path: str):
    """narration.py가 남긴 단어별 시각을 읽는다"""
    if not narration_path:
        return []
    path = os.path.splitext(narration_path)[0] + ".words.json"
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return []


def group_words(words: list, per_line: int = WORDS_PER_LINE):
    """
    단어를 두세 개씩 묶는다. 한 단어씩만 띄우면 너무 정신없고,
    문장 통째로 띄우면 말과 안 맞아 보입니다.
    """
    groups = []
    for i in range(0, len(words), per_line):
        chunk = words[i: i + per_line]
        if not chunk:
            continue
        groups.append(
            {
                "start": chunk[0]["start"],
                "end": chunk[-1]["end"],
                "text": " ".join(w["text"] for w in chunk).strip(),
            }
        )
    return groups


def pop_caption_clips(words: list, font: str, total_duration: float):
    """
    말에 맞춰 톡톡 튀어나오는 자막.
    나타나는 순간에 살짝 커졌다가 제자리로 돌아오게 해서 눈에 걸리게 합니다.
    """
    if not words or not font:
        return []

    clips = []
    for group in group_words(words):
        start = group["start"]
        end = min(group["end"] + 0.12, total_duration)
        length = end - start
        if length <= 0.05 or not group["text"]:
            continue

        try:
            text = TextClip(
                font=font, text=group["text"], font_size=72, color="white",
                stroke_color="black", stroke_width=8,
                method="caption", size=(SHORTS_SIZE[0] - 140, None), text_align="center",
            )
        except Exception as e:
            print(f"[경고] 단어 자막을 만들 수 없어 넘어갑니다 ({e}).")
            return []

        pop = 0.12  # 이 시간 동안 커졌다가 돌아옵니다

        def scale(t, length=length, pop=pop):
            if t >= pop:
                return 1.0
            # 시작하자마자 확 커졌다가 빠르게 제자리로
            return 1.0 + (WORD_POP_SCALE - 1.0) * (1 - t / pop)

        clips.append(
            CompositeVideoClip(
                [text.resized(scale).with_position("center")],
                size=(SHORTS_SIZE[0], CAPTION_H),
            )
            .with_duration(length)
            .with_start(start)
            .with_position(("center", CAPTION_Y))
        )

    return clips


def product_segment(product: dict, hook: str, font: str, cache_dir: str, seconds: float,
                    show_name: bool = True):
    """상품 하나를 보여주는 한 구간"""
    image = fetch_image(product["image"], cache_dir)
    frame = compose_frame(image)

    base = ImageClip(frame).with_duration(seconds)
    # 아주 느린 확대. 정지 사진처럼 보이지 않게 합니다.
    zoomed = base.resized(lambda t: 1 + 0.05 * (t / seconds))
    background = CompositeVideoClip(
        [zoomed.with_position("center")], size=SHORTS_SIZE
    ).with_duration(seconds)

    layers = [background]
    if font:
        layers.append(text_clip(hook, font, 86, HOOK_Y, seconds))
        # 말에 맞춘 자막을 쓸 때는 상품 이름을 빼야 합니다. 같은 자리에 겹쳐
        # 글자가 뭉개지고, 나레이션이 어차피 이름을 읽어줍니다.
        if show_name:
            layers.append(text_clip(product["short_name"][:34], font, 58, CAPTION_Y, seconds))
        layers.append(
            text_clip(f"{product['price']:,}원", font, 104, PRICE_Y, seconds,
                      color="#FFE14D", stroke=7)
        )
        if product.get("rocket"):
            layers.append(text_clip("로켓배송", font, 44, ROCKET_Y, seconds,
                                    color="#7FD4FF", stroke=5))

    return CompositeVideoClip(layers, size=SHORTS_SIZE).with_duration(seconds)


def outro_segment(font: str, seconds: float):
    """마지막 안내 화면. 수수료 고지는 반드시 들어갑니다."""
    from moviepy import ColorClip

    base = ColorClip(SHORTS_SIZE, color=(12, 12, 16), duration=seconds)
    if not font:
        return base

    return CompositeVideoClip(
        [
            base,
            text_clip("구매 링크는", font, 76, 700, seconds),
            text_clip("영상 설명란에", font, 76, 820, seconds, color="#FFE14D"),
            text_clip(DISCLOSURE, font, 32, SHORTS_SIZE[1] - 260, seconds, stroke=4),
        ],
        size=SHORTS_SIZE,
    ).with_duration(seconds)


def find_music(explicit):
    import glob

    if explicit:
        if not os.path.exists(explicit):
            raise SystemExit(f"음악 파일이 없습니다: {explicit}")
        return explicit
    for pattern in MUSIC_EXTS:
        found = sorted(glob.glob(os.path.join(MUSIC_DIR, pattern)))
        if found:
            return found[0]
    return None


def build(products: list, output: str, narration: str, music: str, font: str,
          seconds_per_product: float, cache_dir: str, use_sfx: bool = True,
          pop_captions: bool = True):
    # 말에 맞춘 자막을 쓸 수 있는지 먼저 확인합니다. 쓰면 상품 이름은 빼야
    # 같은 자리에서 겹치지 않습니다.
    words = load_word_timings(narration) if pop_captions else []
    show_name = not bool(words)

    segments = []
    for i, product in enumerate(products):
        hook = HOOKS[i % len(HOOKS)]
        try:
            segments.append(
                product_segment(product, hook, font, cache_dir, seconds_per_product, show_name)
            )
        except Exception as e:
            print(f"[경고] 상품을 건너뜁니다: {product.get('short_name', '')[:30]} ({e})")

    if not segments:
        raise SystemExit("쓸 수 있는 상품이 하나도 없습니다. 이미지 주소를 확인하세요.")

    segments.append(outro_segment(font, OUTRO_SECONDS))

    faded = [segments[0]] + [s.with_effects([vfx.CrossFadeIn(CROSSFADE)]) for s in segments[1:]]
    video = concatenate_videoclips(faded, method="compose", padding=-CROSSFADE)
    duration = video.duration

    # 장면이 바뀌는 시각을 기억해뒀다가 효과음을 얹습니다
    switch_times = []
    elapsed = 0.0
    for segment in segments[:-1]:
        elapsed += segment.duration - CROSSFADE
        if 0 < elapsed < duration:
            switch_times.append(elapsed)

    tracks = []
    if narration and os.path.exists(narration):
        voice = AudioFileClip(narration)
        tracks.append(voice)
        print(f"나레이션: {os.path.basename(narration)} ({voice.duration:.1f}초)")

    if use_sfx and switch_times:
        try:
            sfx_path = find_sfx()
            for moment in switch_times:
                hit = AudioFileClip(sfx_path).with_effects([afx.MultiplyVolume(0.35)])
                tracks.append(hit.with_start(max(moment - 0.12, 0)))
            print(f"전환 효과음 {len(switch_times)}번 ({os.path.basename(sfx_path)})")
        except Exception as e:
            print(f"[경고] 효과음을 넣지 못했습니다: {e}")

    music_path = find_music(music)
    if music_path:
        bgm = AudioFileClip(music_path).with_effects(
            [
                afx.AudioLoop(duration=duration),
                afx.MultiplyVolume(MUSIC_VOLUME),
                afx.AudioFadeOut(min(MUSIC_FADEOUT, duration / 2)),
            ]
        )
        tracks.append(bgm)
        print(f"배경음악: {os.path.basename(music_path)}")
    else:
        print(f"배경음악 없음 — {MUSIC_DIR} 폴더에 음악을 넣으면 자동으로 깔립니다.")

    if tracks:
        video = video.with_audio(CompositeAudioClip(tracks) if len(tracks) > 1 else tracks[0])

    # 말에 맞춰 톡톡 튀는 자막
    layers = [video]
    if words:
        caption_clips = pop_caption_clips(words, font, duration)
        if caption_clips:
            layers.extend(caption_clips)
            print(f"말에 맞춘 자막 {len(caption_clips)}묶음")
    elif pop_captions:
        print("단어 타이밍이 없어 상품 이름을 대신 표시합니다 (나레이션을 만들면 자막이 붙습니다).")

    final = CompositeVideoClip(layers, size=SHORTS_SIZE) if len(layers) > 1 else video

    out_dir = os.path.dirname(output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    print(f"렌더링 중 ({duration:.1f}초, {SHORTS_SIZE[0]}x{SHORTS_SIZE[1]})... → {output}")
    temp_audio = os.path.splitext(output)[0] + ".temp-audio.m4a"
    try:
        final.write_videofile(
            output, fps=30, codec="libx264", audio_codec="aac", threads=4,
            temp_audiofile=temp_audio, remove_temp=True,
        )
    finally:
        final.close()

    return duration


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--products", required=True, help="product_picker.py가 만든 products.json")
    parser.add_argument("--start", type=int, default=0, help="이 순번부터 사용")
    parser.add_argument("--count", type=int, default=3, help="한 영상에 넣을 상품 개수")
    parser.add_argument("--output", required=True)
    parser.add_argument("--narration", default=None)
    parser.add_argument("--music", default=None)
    parser.add_argument("--font", default=None)
    parser.add_argument("--seconds-per-product", type=float, default=SECONDS_PER_PRODUCT)
    parser.add_argument("--cache-dir", default=os.path.join(PROJECT_ROOT, "assets", "product_images"))
    parser.add_argument("--no-sfx", action="store_true", help="장면 전환 효과음 끄기")
    parser.add_argument("--no-pop-captions", action="store_true", help="말에 맞춘 자막 끄기")
    args = parser.parse_args()

    with open(args.products, "r", encoding="utf-8") as f:
        all_products = json.load(f)

    products = all_products[args.start: args.start + args.count]
    if not products:
        raise SystemExit(f"{args.products}에 {args.start}번부터 쓸 상품이 없습니다.")

    font = args.font or find_korean_font()
    if not font:
        print("[경고] 한글 폰트를 찾지 못해 글자 없이 만듭니다. --font로 지정하세요.")

    print(f"상품 {len(products)}개로 쇼츠 구성")
    for p in products:
        print(f"  {p['price']:>8,}원  {p['short_name'][:40]}")

    build(products, args.output, args.narration, args.music, font,
          args.seconds_per_product, args.cache_dir,
          use_sfx=not args.no_sfx, pop_captions=not args.no_pop_captions)
    print(f"완료: {args.output}")


if __name__ == "__main__":
    main()
