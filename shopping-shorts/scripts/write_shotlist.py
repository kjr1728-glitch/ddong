"""
0단계: 샷리스트 만들기

두 가지 방법이 있습니다.
  (권장, 무료) 이 스크립트가 출력하는 요청문을 Claude Code에 붙여넣고 shotlist.json 을 받는다.
  (무인 자동화) ANTHROPIC_API_KEY 가 있으면 --auto 로 API가 바로 만든다 (종량 과금).

사용법:
    python write_shotlist.py --product "무선 전동 청소솔" --features "버튼 하나로 작동,헤드 3종,방수" \
        --image assets/product.png --output shotlist.json
    python write_shotlist.py --url https://쇼핑몰/제품페이지     # 페이지 글 + 대표 이미지 자동 수집
    python write_shotlist.py ... --auto          # API로 자동 생성

--url 은 페이지의 본문 텍스트와 대표 이미지(og:image)를 가져와 요청문에 넣습니다.
쿠팡·스마트스토어처럼 봇을 막거나 자바스크립트로 그리는 페이지는 못 읽을 수 있는데,
그럴 땐 URL 을 Claude Code 에 직접 주고 shotlist.json 을 만들어 달라고 하면 됩니다.
"""
import argparse
import html
import json
import os
import re
import sys

from dotenv import load_dotenv

_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_HERE, "..", ".env"))

MODEL = "claude-opus-5"

MAX_PAGE_CHARS = 6000
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


def fetch_product_page(url: str) -> dict:
    """제품 페이지에서 제목, 본문 텍스트, 대표 이미지 URL 을 뽑는다 (외부 파서 없이)"""
    import requests

    r = requests.get(url, headers=BROWSER_HEADERS, timeout=30)
    r.raise_for_status()
    # 서버가 charset 을 안 알려주면 requests 가 latin-1 로 읽어 한글이 깨집니다.
    if "charset" not in r.headers.get("Content-Type", "").lower():
        m = re.search(rb'charset=["\']?([\w-]+)', r.content[:4096], re.I)
        r.encoding = m.group(1).decode("ascii", "ignore") if m else "utf-8"
    page = r.text

    def meta(prop):
        m = re.search(r'<meta[^>]+(?:property|name)=["\']' + prop + r'["\'][^>]+content=["\']([^"\']+)', page, re.I)
        if not m:
            m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']' + prop + r'["\']', page, re.I)
        return html.unescape(m.group(1)).strip() if m else ""

    title = meta("og:title") or ""
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
        title = html.unescape(m.group(1)).strip() if m else ""
    description = meta("og:description") or meta("description")
    image = meta("og:image")

    body = re.sub(r"<(script|style|noscript|svg|header|footer|nav)[^>]*>.*?</\1>", " ", page, flags=re.I | re.S)
    body = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</h\d>|</tr>", "\n", body, flags=re.I)
    body = re.sub(r"<[^>]+>", " ", body)
    body = html.unescape(body)
    lines = [re.sub(r"[ \t\u00a0]+", " ", ln).strip() for ln in body.splitlines()]
    lines = [ln for ln in lines if len(ln) >= 4]
    text = "\n".join(dict.fromkeys(lines))  # 중복 줄 제거, 순서 유지
    if len(text) > MAX_PAGE_CHARS:
        text = text[:MAX_PAGE_CHARS] + "\n...(이하 생략)"
    return {"url": url, "title": title, "description": description, "image": image, "text": text}


def download_image(url: str, dest: str) -> str:
    import requests

    r = requests.get(url, headers=BROWSER_HEADERS, timeout=30)
    r.raise_for_status()
    ctype = r.headers.get("Content-Type", "")
    ext = ".jpg" if "jpeg" in ctype or "jpg" in ctype else ".png" if "png" in ctype else ".webp" if "webp" in ctype else os.path.splitext(dest)[1] or ".jpg"
    dest = os.path.splitext(dest)[0] + ext
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    with open(dest, "wb") as f:
        f.write(r.content)
    return dest

SYSTEM_PROMPT = """당신은 쇼핑 쇼츠(세로 15~30초 제품 리뷰 영상) 전문 연출가입니다.
AI 영상 모델(Wan 2.2 image-to-video)이 제품 사진 한 장에서 5초짜리 클립을 만들 수 있도록
샷별 영어 모션 프롬프트와 한국어 나레이션을 JSON으로 작성합니다."""


def build_request(product: str, features: list, image: str, shots: int, style: str, tagline: str,
                  page: dict = None) -> str:
    feat = "\n".join(f"- {f}" for f in features) or "- (특징 미입력)"
    page_block = ""
    if page:
        page_block = f"""
[제품 페이지에서 가져온 정보] {page['url']}
제목: {page.get('title') or '(없음)'}
요약: {page.get('description') or '(없음)'}
본문:
{page.get('text') or '(본문을 읽지 못함)'}

위 페이지 정보에서 실제 사용 방법(버튼 위치, 켜는 법, 교체 방법 등)을 찾아
샷의 동작 프롬프트와 나레이션에 정확히 반영할 것. 페이지에 없는 기능은 지어내지 말 것.
"""
    style_note = {
        "hand": "얼굴 없이 실제 사람 손만 나오는 UGC 리뷰 형식. type 은 'hand' 와 'product' 만 사용.",
        "face": "리뷰어 얼굴이 나오는 UGC 형식. 첫 샷과 마지막 샷은 type 'face', 나머지는 'hand'/'product'. "
                "face 샷에는 start_image 자리에 \"assets/character.png\" 를 넣을 것.",
        "product": "사람 없이 제품만 보여주는 형식. type 은 'product' 만 사용.",
    }[style]
    return f"""아래 제품의 쇼핑 쇼츠 샷리스트를 JSON 하나로만 답해주세요 (설명 없이 JSON만).

제품명: {product}
한 줄 카피(선택): {tagline or "(없음)"}
특징:
{feat}
제품 사진 경로: {image}
샷 수: {shots}개 (샷당 약 5초)
형식: {style_note}

JSON 형식:
{{
  "product": {{"name": "...", "tagline": "화면 위에 뜰 짧은 카피", "image": "{image}"}},
  "video": {{"workflow": "wan22_5b_i2v", "width": 704, "height": 1280, "length": 121, "fps": 24, "seed": 1234}},
  "voice": "ko-KR-SunHiNeural",
  "style": "{style}",
  "shots": [
    {{"id": "01", "type": "hand|product|face", "prompt": "영어 모션 프롬프트", "narration": "한국어 한두 문장"}}
  ]
}}

프롬프트 작성 규칙:
1. 영어로, 카메라 움직임과 손/제품의 동작을 구체적으로 (예: "a hand reaches in and picks up...", "camera slowly pushes in").
2. 시작 프레임은 제품 사진이므로, 첫 순간에 제품이 화면 가운데 놓여 있다고 가정하고 거기서 시작하는 동작을 쓸 것.
3. 텍스트, 로고, 자막을 그리라는 말은 넣지 말 것 (AI가 글자를 망가뜨림).
4. 나레이션은 구어체, 샷당 12~25자, 첫 샷은 후킹 질문, 마지막 샷은 행동 유도.
5. 나레이션에 괄호나 지시문을 넣지 말 것 (그대로 음성으로 읽힘).
{page_block}"""


def generate_with_api(request: str) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit(
            "ANTHROPIC_API_KEY 가 없습니다. --auto 를 빼고 실행해서 나오는 요청문을 "
            "Claude Code 에 붙여넣으면 무료로 만들 수 있습니다."
        )
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": request}],
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    ) as stream:
        message = stream.get_final_message()
    if message.stop_reason == "refusal":
        raise SystemExit("모델이 요청을 거절했습니다. 제품 설명을 바꿔 다시 시도해 주세요.")
    text = "\n".join(b.text for b in message.content if b.type == "text").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise SystemExit(f"JSON 을 찾지 못했습니다:\n{text[:500]}")
    return json.loads(text[start:end + 1])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", default=None, help="제품명 (--url 이 있으면 페이지 제목으로 대체 가능)")
    parser.add_argument("--url", default=None, help="제품 페이지 주소. 본문과 대표 이미지를 자동으로 가져옵니다")
    parser.add_argument("--features", default="", help="쉼표로 구분")
    parser.add_argument("--tagline", default="")
    parser.add_argument("--image", default="assets/product.png")
    parser.add_argument("--shots", type=int, default=5)
    parser.add_argument("--style", default="hand", choices=["hand", "face", "product"])
    parser.add_argument("--output", default="shotlist.json")
    parser.add_argument("--auto", action="store_true", help="Anthropic API 로 바로 생성 (종량 과금)")
    args = parser.parse_args()

    features = [f.strip() for f in args.features.split(",") if f.strip()]

    page = None
    if args.url:
        try:
            page = fetch_product_page(args.url)
        except Exception as e:
            raise SystemExit(
                f"페이지를 읽지 못했습니다 ({e}).\n"
                "이 사이트는 봇 접근을 막거나 자바스크립트로 내용을 그리는 것 같습니다.\n"
                "→ URL 을 Claude Code 에 직접 주고 shotlist.json 을 만들어 달라고 하세요."
            )
        print(f"페이지 읽음: {page['title'] or args.url} (본문 {len(page['text'])}자)")
        if not args.product:
            args.product = page["title"] or args.url
        if page["image"]:
            try:
                saved = download_image(page["image"], args.image)
                args.image = os.path.relpath(saved, os.path.dirname(os.path.abspath(args.output)) or ".").replace("\\", "/")
                print(f"대표 이미지 저장: {saved}  (다른 사진이 더 낫다면 이 파일을 바꿔치기 하세요)")
            except Exception as e:
                print(f"[경고] 대표 이미지를 받지 못했습니다: {e} — assets/product.png 에 직접 넣어주세요")
        if not page["text"]:
            print("[경고] 본문을 거의 읽지 못했습니다. --features 로 사용법을 직접 적어주세요.")
    if not args.product:
        raise SystemExit("--product 또는 --url 중 하나는 필요합니다.")

    request = build_request(args.product, features, args.image, args.shots, args.style, args.tagline, page)

    if not args.auto:
        print("아래 내용을 Claude Code 에 그대로 붙여넣고, 답으로 받은 JSON 을")
        print(f"  {os.path.abspath(args.output)}")
        print("에 저장하세요. (API 과금 없이 Claude Code 구독만으로 가능)\n")
        print("=" * 70)
        print(request)
        print("=" * 70)
        return

    data = generate_with_api(request)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"완료: {args.output} (샷 {len(data.get('shots', []))}개)")


if __name__ == "__main__":
    main()
