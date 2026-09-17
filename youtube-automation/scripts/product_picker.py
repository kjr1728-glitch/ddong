"""
쇼츠에 쓸 상품 고르기

"1~2초 안에 어? 저거 괜찮은데" 소리가 나오려면 상품 자체가 그런 물건이어야
합니다. 사람이 고르는 기준을 점수로 옮긴 것이 이 파일입니다.

기준
- 한눈에 뭔지 알아야 한다: 이름이 너무 길거나 옵션 나열인 상품은 감점
- 충동구매 가능한 가격: 만원 안팎이 제일 잘 먹히고, 너무 싸거나 비싸면 감점
- 신기해 보여야 한다: 생수, 휴지 같은 생필품 반복구매 상품은 제외
- 바로 살 수 있어야 한다: 로켓배송 가산점
- 같은 상품을 또 올리지 않는다: 이미 쓴 상품 기록

사용법:
    python scripts/product_picker.py --count 9
"""
import argparse
import json
import os
import random
import re
from datetime import datetime, timezone

from coupang_client import CATEGORIES, CoupangError, CoupangPartners, normalize

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_FILE = os.path.join(PROJECT_ROOT, "output", ".used_products.json")

# 신기한 물건이 잘 나오는 카테고리를 우선으로 봅니다
DEFAULT_CATEGORIES = ["생활용품", "주방용품", "가전디지털", "홈인테리어", "완구취미", "문구오피스", "자동차용품"]

# 영상으로 만들어도 호기심이 안 생기는 종류. 이름에 들어가면 거릅니다.
BORING_WORDS = [
    "생수", "휴지", "화장지", "키친타올", "키친타월", "물티슈", "세제", "섬유유연제",
    "기저귀", "분유", "쌀", "라면", "비닐봉투", "지퍼백", "종이컵",
    "즉석밥", "커피믹스", "종량제", "리필", "대용량", "묶음", "박스", "세트할인",
    "상품권", "기프트카드", "충전권", "이용권", "정기배송",
]

# 이름에 이런 말이 있으면 "뭐지?" 하고 보게 됩니다
CURIOUS_WORDS = [
    "접이식", "휴대용", "미니", "무선", "자동", "1초", "원터치", "각도조절", "회전",
    "실리콘", "논슬립", "초소형", "다용도", "만능", "틈새", "차량용", "usb", "충전식",
    "led", "센서", "방수", "정리", "수납", "거치대", "클리너", "커터", "홀더",
]

PRICE_SWEET_SPOT = (7000, 39000)   # 이 구간이 충동구매가 가장 잘 일어납니다
PRICE_HARD_LIMITS = (3000, 90000)  # 이 밖은 아예 제외


def load_history() -> set:
    if not os.path.exists(HISTORY_FILE):
        return set()
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f).get("used_ids", []))
    except (ValueError, OSError):
        return set()


def save_history(used: set, added: list):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "used_ids": sorted(used),
                "last_added": added,
            },
            f, ensure_ascii=False, indent=2,
        )


def clean_name(name: str) -> str:
    """상품명에서 괄호 옵션과 판촉 문구를 걷어낸다. 자막에 그대로 쓸 수 있게."""
    name = re.sub(r"\[[^\]]*\]", " ", name)
    name = re.sub(r"\([^)]*\)", " ", name)
    name = re.sub(r"\s*[,/]\s*\d+\s*(개|매|입|팩|세트|개입).*$", "", name)
    return re.sub(r"\s+", " ", name).strip()


def score(product: dict) -> float:
    """높을수록 쇼츠에 쓰기 좋은 상품"""
    name = product["name"]
    lowered = name.lower()
    price = product["price"]

    if any(word in name for word in BORING_WORDS):
        return -1.0
    if not (PRICE_HARD_LIMITS[0] <= price <= PRICE_HARD_LIMITS[1]):
        return -1.0
    if not product["image"]:
        return -1.0

    points = 0.0

    # 가격: 충동구매 구간에 가까울수록 높게
    if PRICE_SWEET_SPOT[0] <= price <= PRICE_SWEET_SPOT[1]:
        points += 3.0
    else:
        points += 1.0

    # 한눈에 읽히는 이름일수록 좋습니다
    short_name = clean_name(name)
    if len(short_name) <= 20:
        points += 2.0
    elif len(short_name) <= 32:
        points += 1.0

    # "어? 저게 뭐야" 싶은 단어가 들어 있으면 가산점
    hits = sum(1 for word in CURIOUS_WORDS if word in lowered)
    points += min(hits, 3) * 1.2

    if product["rocket"]:
        points += 1.5
    if product["free_shipping"]:
        points += 0.3

    return points


def collect_candidates(client: CoupangPartners, categories: list, per_category: int) -> list:
    """골드박스와 카테고리 베스트를 섞어서 후보를 모은다"""
    seen = {}

    try:
        for item in client.goldbox():
            p = normalize(item)
            if p["id"]:
                seen[p["id"]] = p
        print(f"  골드박스에서 {len(seen)}개")
    except CoupangError as e:
        print(f"  [경고] 골드박스 조회 실패, 건너뜁니다: {e}")

    for name in categories:
        category_id = CATEGORIES.get(name)
        if not category_id:
            print(f"  [경고] 모르는 카테고리, 건너뜁니다: {name}")
            continue
        try:
            items = client.best_category(category_id, limit=per_category)
        except CoupangError as e:
            print(f"  [경고] '{name}' 조회 실패, 건너뜁니다: {e}")
            continue
        before = len(seen)
        for item in items:
            p = normalize(item)
            if p["id"]:
                seen.setdefault(p["id"], p)
        print(f"  {name}에서 {len(seen) - before}개 추가")

    return list(seen.values())


def pick(client: CoupangPartners, count: int, categories: list, per_category: int) -> list:
    print("상품 후보 수집 중...")
    candidates = collect_candidates(client, categories, per_category)
    if not candidates:
        raise SystemExit("상품을 하나도 받지 못했습니다. API 키와 네트워크를 확인하세요.")

    used = load_history()
    scored = []
    for product in candidates:
        if product["id"] in used:
            continue
        value = score(product)
        if value > 0:
            product["score"] = value
            product["short_name"] = clean_name(product["name"])
            scored.append(product)

    if not scored:
        raise SystemExit(
            "쓸 만한 상품이 없습니다. 이미 다 써버렸거나 조건이 너무 좁습니다.\n"
            f"기록을 지우려면 {HISTORY_FILE} 파일을 삭제하세요."
        )

    # 점수 상위권에서 무작위로 뽑습니다. 매번 똑같은 상품만 나오지 않게.
    scored.sort(key=lambda p: p["score"], reverse=True)
    pool = scored[: max(count * 4, 20)]
    random.shuffle(pool)
    chosen = pool[:count]

    print(f"\n후보 {len(scored)}개 중 {len(chosen)}개 선정")
    return chosen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=9, help="고를 상품 개수")
    parser.add_argument(
        "--categories", default=",".join(DEFAULT_CATEGORIES),
        help="쉼표로 구분된 카테고리 이름",
    )
    parser.add_argument("--per-category", type=int, default=30)
    parser.add_argument("--output", default=os.path.join(PROJECT_ROOT, "output", "products.json"))
    parser.add_argument("--no-history", action="store_true", help="이미 쓴 상품도 다시 고름")
    args = parser.parse_args()

    client = CoupangPartners()
    categories = [c.strip() for c in args.categories.split(",") if c.strip()]

    if args.no_history:
        globals()["load_history"] = lambda: set()

    chosen = pick(client, args.count, categories, args.per_category)

    for product in chosen:
        print(f"  {product['score']:4.1f}점  {product['price']:>8,}원  {product['short_name'][:40]}")

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(chosen, f, ensure_ascii=False, indent=2)

    print(f"\n저장: {args.output}")


if __name__ == "__main__":
    main()
