"""
상품을 직접 골라 쇼츠 만들기 (쿠팡 API 없이)

쿠팡 파트너스 API는 최종 승인(누적 판매 15만원)을 받아야 쓸 수 있습니다.
그전까지는 이 방법으로 직접 상품을 넣어 영상을 만드세요.
매출이 쌓여 API가 열리면 shorts.py가 알아서 자동으로 골라옵니다.

준비물
1. assets/my_products/ 폴더에 상품 이미지 저장
   (쿠팡 상품 페이지에서 대표 이미지를 오른쪽 클릭 → 이미지 저장)
2. assets/my_products/products.csv 에 상품 정보 입력
   (엑셀이나 메모장으로 열어서 한 줄에 상품 하나씩)

CSV 형식 (첫 줄은 그대로 두세요):
    이미지파일,상품명,가격,링크,로켓배송
    fan.jpg,접이식 휴대용 미니 선풍기,12900,https://link.coupang.com/a/XXXX,Y

- 이미지파일: 같은 폴더에 있는 파일 이름만 적으면 됩니다
- 가격: 숫자만 (쉼표 없이)
- 링크: 쿠팡 파트너스 사이트에서 만든 내 추천 링크
- 로켓배송: 맞으면 Y, 아니면 비워두세요

사용법:
    python scripts/manual_products.py
    python shorts.py --manual
"""
import argparse
import csv
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DIR = os.path.join(PROJECT_ROOT, "assets", "my_products")
DEFAULT_CSV = os.path.join(DEFAULT_DIR, "products.csv")

TEMPLATE = """이미지파일,상품명,가격,링크,로켓배송
예시.jpg,접이식 휴대용 미니 선풍기,12900,https://link.coupang.com/a/XXXXXX,Y
"""


def clean_name(name: str) -> str:
    import re

    name = re.sub(r"\[[^\]]*\]", " ", name)
    name = re.sub(r"\([^)]*\)", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def load_csv(csv_path: str, image_dir: str) -> list:
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    products = []
    problems = []

    for line_no, row in enumerate(rows, start=2):
        filename = (row.get("이미지파일") or "").strip()
        name = (row.get("상품명") or "").strip()
        price_text = (row.get("가격") or "").strip().replace(",", "").replace("원", "")
        link = (row.get("링크") or "").strip()
        rocket = (row.get("로켓배송") or "").strip().upper() in ("Y", "YES", "O", "네", "예")

        if not any([filename, name, price_text]):
            continue  # 빈 줄은 넘어갑니다

        if filename.startswith("예시"):
            continue  # 안내용 예시 줄은 건너뜁니다

        image_path = filename if os.path.isabs(filename) else os.path.join(image_dir, filename)

        if not filename:
            problems.append(f"{line_no}번째 줄: 이미지파일이 비어 있습니다")
            continue
        if not os.path.exists(image_path):
            problems.append(f"{line_no}번째 줄: 이미지를 찾을 수 없습니다 → {image_path}")
            continue
        if not name:
            problems.append(f"{line_no}번째 줄: 상품명이 비어 있습니다")
            continue
        try:
            price = int(float(price_text))
        except ValueError:
            problems.append(f"{line_no}번째 줄: 가격이 숫자가 아닙니다 → '{price_text}'")
            continue
        if not link:
            problems.append(f"{line_no}번째 줄: 링크가 비어 있습니다 (수수료를 받으려면 필요합니다)")

        products.append(
            {
                "id": f"manual-{line_no}",
                "name": name,
                "short_name": clean_name(name),
                "price": price,
                "image": image_path,
                "url": link,
                "link": link,
                "rocket": rocket,
                "free_shipping": False,
                "category": "",
                "score": 0.0,
            }
        )

    return products, problems


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=DEFAULT_CSV)
    parser.add_argument("--image-dir", default=None, help="기본값: CSV가 있는 폴더")
    parser.add_argument("--output", default=os.path.join(PROJECT_ROOT, "output", "products.json"))
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        os.makedirs(os.path.dirname(args.csv), exist_ok=True)
        with open(args.csv, "w", encoding="utf-8-sig") as f:
            f.write(TEMPLATE)
        sys.exit(
            f"상품 목록 파일을 새로 만들었습니다:\n  {args.csv}\n\n"
            "이 파일을 엑셀이나 메모장으로 열어 상품을 적어주세요.\n"
            f"상품 이미지는 같은 폴더({os.path.dirname(args.csv)})에 저장하시면 됩니다.\n"
            "다 적으신 뒤 이 명령을 다시 실행하세요."
        )

    image_dir = args.image_dir or os.path.dirname(os.path.abspath(args.csv))
    products, problems = load_csv(args.csv, image_dir)

    for problem in problems:
        print(f"[확인 필요] {problem}")

    if not products:
        sys.exit(
            f"\n쓸 수 있는 상품이 없습니다. {args.csv} 파일을 확인해주세요.\n"
            "첫 줄(이미지파일,상품명,가격,링크,로켓배송)은 그대로 두고\n"
            "두 번째 줄부터 상품을 적으시면 됩니다."
        )

    print(f"\n상품 {len(products)}개를 읽었습니다.")
    for product in products:
        mark = "로켓" if product["rocket"] else "    "
        print(f"  {mark}  {product['price']:>8,}원  {product['short_name'][:40]}")

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    print(f"\n저장: {args.output}")
    print("이제 python shorts.py --manual 로 영상을 만드세요.")


if __name__ == "__main__":
    main()
