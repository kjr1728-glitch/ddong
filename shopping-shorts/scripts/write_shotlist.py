"""
0단계: 샷리스트 만들기

두 가지 방법이 있습니다.
  (권장, 무료) 이 스크립트가 출력하는 요청문을 Claude Code에 붙여넣고 shotlist.json 을 받는다.
  (무인 자동화) ANTHROPIC_API_KEY 가 있으면 --auto 로 API가 바로 만든다 (종량 과금).

사용법:
    python write_shotlist.py --product "무선 전동 청소솔" --features "버튼 하나로 작동,헤드 3종,방수" \
        --image assets/product.png --output shotlist.json
    python write_shotlist.py ... --auto          # API로 자동 생성
"""
import argparse
import json
import os
import sys

from dotenv import load_dotenv

_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_HERE, "..", ".env"))

MODEL = "claude-opus-5"

SYSTEM_PROMPT = """당신은 쇼핑 쇼츠(세로 15~30초 제품 리뷰 영상) 전문 연출가입니다.
AI 영상 모델(Wan 2.2 image-to-video)이 제품 사진 한 장에서 5초짜리 클립을 만들 수 있도록
샷별 영어 모션 프롬프트와 한국어 나레이션을 JSON으로 작성합니다."""


def build_request(product: str, features: list, image: str, shots: int, style: str, tagline: str) -> str:
    feat = "\n".join(f"- {f}" for f in features) or "- (특징 미입력)"
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
"""


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
    parser.add_argument("--product", required=True)
    parser.add_argument("--features", default="", help="쉼표로 구분")
    parser.add_argument("--tagline", default="")
    parser.add_argument("--image", default="assets/product.png")
    parser.add_argument("--shots", type=int, default=5)
    parser.add_argument("--style", default="hand", choices=["hand", "face", "product"])
    parser.add_argument("--output", default="shotlist.json")
    parser.add_argument("--auto", action="store_true", help="Anthropic API 로 바로 생성 (종량 과금)")
    args = parser.parse_args()

    features = [f.strip() for f in args.features.split(",") if f.strip()]
    request = build_request(args.product, features, args.image, args.shots, args.style, args.tagline)

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
