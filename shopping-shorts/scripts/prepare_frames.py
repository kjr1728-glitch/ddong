"""
1단계: 시작 프레임 준비

Wan 2.2 이미지→영상은 "첫 프레임" 한 장에서 출발합니다.
제품 사진을 영상 크기(기본 704x1280, 9:16)에 맞춰 캔버스에 앉힌 PNG를
샷마다 하나씩 만듭니다. 샷에 start_image 가 따로 있으면 (예: 얼굴 컷의 인물 참조 사진)
그 이미지를 대신 씁니다.

제품 사진은 배경이 단순할수록 좋고, 여백을 넉넉히 두면 손이 들어올 자리가 생깁니다.

사용법:
    python prepare_frames.py --shotlist shotlist.json --out-dir output/run/frames
"""
import argparse
import os

from PIL import Image, ImageFilter

from common import load_shotlist, resolve, video_settings


def fit_on_canvas(src: str, width: int, height: int, mode: str = "blur") -> Image.Image:
    """
    비율을 유지하며 캔버스에 맞춘다.
      blur : 남는 부분을 원본을 크게 흐린 배경으로 채움 (제품 사진에 자연스러움)
      cover: 캔버스를 꽉 채우고 넘치는 부분을 자름 (이미 9:16인 인물 사진용)
    """
    im = Image.open(src).convert("RGB")
    if mode == "cover":
        scale = max(width / im.width, height / im.height)
        resized = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
        left = (resized.width - width) // 2
        top = (resized.height - height) // 2
        return resized.crop((left, top, left + width, top + height))

    scale = min(width / im.width, height / im.height) * 0.82  # 손이 들어올 여백
    fg = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
    bg_scale = max(width / im.width, height / im.height)
    bg = im.resize((round(im.width * bg_scale), round(im.height * bg_scale)), Image.LANCZOS)
    bg = bg.crop(((bg.width - width) // 2, (bg.height - height) // 2,
                  (bg.width - width) // 2 + width, (bg.height - height) // 2 + height))
    bg = bg.filter(ImageFilter.GaussianBlur(radius=max(width, height) // 25))
    # 배경을 살짝 밝게 눌러 제품이 도드라지게
    bg = Image.blend(bg, Image.new("RGB", bg.size, (245, 245, 245)), 0.35)
    canvas = bg
    canvas.paste(fg, ((width - fg.width) // 2, (height - fg.height) // 2))
    return canvas


def prepare(shotlist_path: str, out_dir: str, log=print) -> list:
    data = load_shotlist(shotlist_path)
    base = data["_base_dir"]
    v = video_settings(data)
    width, height = int(v["width"]), int(v["height"])
    if width % 16 or height % 16:
        raise SystemExit(f"width/height 는 16의 배수여야 합니다 (현재 {width}x{height}).")

    product_img = resolve(base, data["product"].get("image", ""))
    if not product_img or not os.path.exists(product_img):
        raise SystemExit(f"제품 사진을 찾을 수 없습니다: {product_img!r} (shotlist의 product.image)")

    os.makedirs(out_dir, exist_ok=True)
    results = []
    for shot in data["shots"]:
        dest = os.path.join(out_dir, f"shot_{shot['id']}.png")
        if os.path.exists(dest):
            log(f"  [건너뜀] {dest}")
            results.append(dest)
            continue
        custom = resolve(base, shot.get("start_image", ""))
        if shot["type"] == "face" and not custom:
            raise SystemExit(
                f"샷 {shot['id']} 은 type=face 인데 start_image 가 없습니다. "
                "같은 인물이 나오는 참조 사진 경로를 넣어주세요 (README '얼굴 컷' 참고)."
            )
        if custom:
            if not os.path.exists(custom):
                raise SystemExit(f"샷 {shot['id']} 의 start_image 를 찾을 수 없습니다: {custom}")
            img = fit_on_canvas(custom, width, height, mode=shot.get("fit", "cover"))
        else:
            img = fit_on_canvas(product_img, width, height, mode=shot.get("fit", "blur"))
        img.save(dest, "PNG")
        log(f"  프레임 생성: {dest}")
        results.append(dest)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shotlist", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    frames = prepare(args.shotlist, args.out_dir)
    print(f"완료: 시작 프레임 {len(frames)}장 → {args.out_dir}")


if __name__ == "__main__":
    main()
