"""
스크립트 작성 (선택사항 — API 종량 과금)

기본 권장 경로: output/trends.json을 Claude Code에게 보여주고 직접 대화로
스크립트를 받는 것 (구독료 안에 포함, 추가 비용 없음).

이 스크립트는 파이프라인을 완전히 무인 자동화(cron 등)하고 싶을 때만 쓰세요.
Anthropic API는 사용량만큼 과금되므로 "완전 무료"는 아닙니다.

사용법:
    python script_writer.py --trends output/trends.json --minutes 5
"""
import argparse
import json
import os

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

MODEL = "claude-opus-5"

SYSTEM_PROMPT = """당신은 한국어 유튜브 롱폼 콘텐츠 전문 작가입니다.
"호기심 자극형(사실/정보)" 니치에 맞는, 후킹이 강하고 끝까지 듣게 만드는
내레이션 스크립트를 작성합니다. 자막으로도 쓰일 수 있도록 문장을 짧고
명확하게 씁니다. 광고나 협찬 문구는 넣지 않습니다."""


def build_user_prompt(trends: dict, minutes: int) -> str:
    top_titles = [v["title"] for v in trends.get("top_videos", [])[:8]]
    rising = [
        q.get("query", "")
        for q in trends.get("google_trends", {}).get("related_queries", {}).get("rising", [])[:5]
    ]

    titles_block = "\n".join("- " + t for t in top_titles) or "- (데이터 없음)"
    rising_block = "\n".join("- " + r for r in rising if r) or "- (데이터 없음)"

    return f"""다음 데이터를 참고해서 "{trends['keyword']}" 주제로
약 {minutes}분 분량(1분당 약 350~400자 기준)의 유튜브 롱폼 내레이션 스크립트를 써주세요.

[현재 인기 있는 관련 영상 제목들]
{titles_block}

[떠오르는 연관 검색어]
{rising_block}

요구사항:
1. 처음 10초 안에 강력한 후킹 (질문, 반전, 충격적 사실 등)
2. 도입 - 전개(3~4개 소주제) - 마무리(여운/질문) 구조
3. 각 문단 앞에 [SECTION: 한글 소주제명 | english search keywords] 형식의 태그를 넣을 것.
   파이프(|) 뒤의 영어 키워드는 무료 스톡 영상 검색에 그대로 쓰이므로,
   화면에 깔릴 배경 영상을 떠올리며 2~4단어의 구체적인 영어 표현으로 적어주세요.
   (예: [SECTION: 밤하늘의 비밀 | night sky stars timelapse])
4. 구어체, 문장은 짧게
5. 태그 외의 본문에는 대괄호나 괄호 안 지시문을 쓰지 말 것 (그대로 음성으로 읽힙니다)
"""


def generate_script(trends_path: str, minutes: int) -> str:
    if not ANTHROPIC_API_KEY:
        raise SystemExit(
            "ANTHROPIC_API_KEY가 설정되지 않았습니다.\n"
            "→ 대신 output/trends.json 내용을 Claude Code에게 붙여넣고 직접 스크립트를 요청하세요 (무료)."
        )

    import anthropic

    with open(trends_path, "r", encoding="utf-8") as f:
        trends = json.load(f)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # 스트리밍을 쓰는 이유: 긴 출력에서 HTTP 타임아웃을 피하기 위해서입니다.
    # fallbacks는 안전 분류기가 요청을 거절했을 때 다른 모델로 자동 재시도하는
    # 서버 측 옵션입니다. 무인 실행 중 한 번의 거절로 파이프라인이 멈추지 않게 해줍니다.
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_prompt(trends, minutes)}],
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise SystemExit(
            "모델이 이 요청을 거절했습니다. 주제나 키워드를 바꿔서 다시 시도해 주세요."
        )

    parts = [block.text for block in message.content if block.type == "text"]
    script = "\n".join(parts).strip()
    if not script:
        raise SystemExit("빈 응답을 받았습니다. 다시 시도해 주세요.")

    return script


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trends", default="output/trends.json")
    parser.add_argument("--minutes", type=int, default=5)
    parser.add_argument("--output", default="output/script.txt")
    args = parser.parse_args()

    script = generate_script(args.trends, args.minutes)

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(script)

    print(f"완료: {args.output} ({len(script)}자)")


if __name__ == "__main__":
    main()
