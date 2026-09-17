"""
쇼핑 쇼츠 자동 제작 — 상품 선별부터 업로드까지

하루치를 한 번에 만듭니다. 기본은 영상 3개, 영상마다 상품 3개입니다.

    python shorts.py                      # 영상 3개 만들기 (업로드 안 함)
    python shorts.py --upload             # 만들고 비공개로 업로드까지
    python shorts.py --videos 3 --per-video 3

만들어진 영상은 output/shorts/<날짜>/ 안에 들어갑니다.

업로드는 기본이 비공개입니다. 확인하지 않은 영상이 자동으로 전체 공개되는 것을
막기 위해서입니다. 공개로 올리려면 --privacy public을 직접 붙여야 합니다.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

DISCLOSURE = "이 영상은 쿠팡 파트너스 활동의 일환으로 수수료를 제공받습니다"


def run(cmd: list):
    print(f"\n$ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(f"실패: {' '.join(str(c) for c in cmd)}")


def script_path(name: str) -> str:
    return os.path.join(SCRIPTS_DIR, name)


def narration_text(products: list) -> str:
    """상품 정보로 읽을 대사를 만든다. 짧고 끊어지게."""
    lines = ["이거 왜 이제 알았지 싶은 물건들이요."]
    for product in products:
        lines.append(f"{product['short_name']}. {product['price']:,}원이에요.")
    lines.append("링크는 설명란에 있어요.")
    return "\n".join(lines)


def build_description(products: list) -> str:
    """영상 설명란. 수수료 고지 문구가 맨 위에 옵니다."""
    lines = [DISCLOSURE, ""]
    for i, product in enumerate(products, 1):
        lines.append(f"{i}. {product['short_name']} / {product['price']:,}원")
        lines.append(f"   {product.get('link') or product['url']}")
        lines.append("")
    lines.append("#쇼츠 #쿠팡 #꿀템 #생활용품 #자취템")
    return "\n".join(lines)


def build_title(products: list) -> str:
    lead = products[0]["short_name"][:24] if products else "오늘의 꿀템"
    return f"{lead} 이거 왜 이제 알았지 #Shorts"[:100]


def add_affiliate_links(products: list):
    """일반 쿠팡 주소를 수수료가 붙는 파트너스 링크로 바꾼다"""
    try:
        from coupang_client import CoupangPartners

        client = CoupangPartners()
        urls = [p["url"] for p in products if p.get("url")]
        if not urls:
            return
        results = client.deeplink(urls)
        mapping = {
            r.get("originalUrl"): r.get("shortenUrl") or r.get("landingUrl")
            for r in results if isinstance(r, dict)
        }
        for product in products:
            link = mapping.get(product.get("url"))
            if link:
                product["link"] = link
        print(f"파트너스 링크 {sum(1 for p in products if p.get('link'))}개 생성")
    except Exception as e:
        # 링크 변환이 실패해도 영상은 만들 수 있게 합니다. 다만 수수료는 안 붙습니다.
        print(f"[경고] 파트너스 링크 변환 실패, 일반 링크를 씁니다: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--videos", type=int, default=3, help="만들 영상 개수")
    parser.add_argument("--per-video", type=int, default=3, help="영상 하나에 넣을 상품 개수")
    parser.add_argument("--seconds-per-product", type=float, default=5.0)
    parser.add_argument("--voice", default="ko-KR-SunHiNeural")
    parser.add_argument("--no-narration", action="store_true", help="목소리 없이 음악만")
    parser.add_argument("--music", default=None)
    parser.add_argument("--font", default=None)
    parser.add_argument("--upload", action="store_true", help="만든 뒤 유튜브에 올리기")
    parser.add_argument(
        "--privacy", default="private", choices=["private", "unlisted", "public"],
        help="업로드 공개 설정. 기본 private",
    )
    parser.add_argument("--run-dir", default=None)
    args = parser.parse_args()

    today = datetime.date.today().isoformat()
    run_dir = args.run_dir or os.path.join(PROJECT_ROOT, "output", "shorts", today)
    os.makedirs(run_dir, exist_ok=True)
    print(f"작업 폴더: {run_dir}")

    needed = args.videos * args.per_video
    products_file = os.path.join(run_dir, "products.json")

    # 1단계: 상품 고르기
    if os.path.exists(products_file):
        print(f"\n[건너뜀] 상품 목록이 이미 있습니다: {products_file}")
    else:
        run([sys.executable, script_path("product_picker.py"),
             "--count", str(needed), "--output", products_file])

    with open(products_file, "r", encoding="utf-8") as f:
        all_products = json.load(f)

    if len(all_products) < args.per_video:
        sys.exit(f"상품이 {len(all_products)}개뿐이라 영상을 만들 수 없습니다.")

    # 2단계: 수수료가 붙는 링크로 변환
    add_affiliate_links(all_products)
    with open(products_file, "w", encoding="utf-8") as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)

    made = []
    for index in range(args.videos):
        start = index * args.per_video
        products = all_products[start: start + args.per_video]
        if len(products) < 1:
            print(f"\n상품이 모자라 {index + 1}번째 영상은 건너뜁니다.")
            break

        print(f"\n===== {index + 1}번째 영상 =====")
        video_file = os.path.join(run_dir, f"short_{index + 1}.mp4")
        narration_file = os.path.join(run_dir, f"narration_{index + 1}.mp3")

        # 나레이션
        if not args.no_narration and not os.path.exists(narration_file):
            text_file = os.path.join(run_dir, f"narration_{index + 1}.txt")
            with open(text_file, "w", encoding="utf-8") as f:
                f.write(narration_text(products))
            run([sys.executable, script_path("narration.py"),
                 "--script", text_file, "--voice", args.voice,
                 "--output", narration_file,
                 "--srt", os.path.join(run_dir, f"narration_{index + 1}.srt")])

        # 영상
        build_cmd = [
            sys.executable, script_path("shorts_builder.py"),
            "--products", products_file,
            "--start", str(start), "--count", str(args.per_video),
            "--seconds-per-product", str(args.seconds_per_product),
            "--output", video_file,
        ]
        if not args.no_narration and os.path.exists(narration_file):
            build_cmd += ["--narration", narration_file]
        if args.music:
            build_cmd += ["--music", args.music]
        if args.font:
            build_cmd += ["--font", args.font]
        run(build_cmd)

        # 제목과 설명란을 파일로 남겨둡니다. 업로드 안 할 때 직접 복사해 쓰기 좋게.
        meta = {
            "title": build_title(products),
            "description": build_description(products),
            "products": products,
        }
        meta_file = os.path.join(run_dir, f"meta_{index + 1}.json")
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        made.append((video_file, meta, meta_file))

    # 3단계: 업로드
    if args.upload:
        for video_file, meta, meta_file in made:
            desc_file = meta_file.replace(".json", "_description.txt")
            with open(desc_file, "w", encoding="utf-8") as f:
                f.write(meta["description"])
            run([sys.executable, script_path("youtube_upload.py"),
                 "--video", video_file,
                 "--title", meta["title"],
                 "--description-file", desc_file,
                 "--tags", "쇼츠,쿠팡,꿀템,생활용품,자취템",
                 "--privacy", args.privacy])

    print(f"\n영상 {len(made)}개 완성 → {run_dir}")
    for video_file, meta, _ in made:
        print(f"  {os.path.basename(video_file)}  |  {meta['title'][:45]}")

    if not args.upload:
        print("\n유튜브에 올리려면 --upload를 붙이세요.")
        print("제목과 설명란은 meta_*.json에 들어 있습니다.")


if __name__ == "__main__":
    main()
