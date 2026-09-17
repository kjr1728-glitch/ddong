"""
나레이션(TTS) 생성 — 완전 무료, API 키 불필요
Microsoft Edge의 온라인 음성 엔진을 사용하는 edge-tts 라이브러리 사용

나레이션 mp3와 함께, 실제 발화 타이밍에 맞춘 자막 파일(.srt)도 같이 만듭니다.
edge-tts가 단어 단위로 알려주는 WordBoundary 정보를 모아 문장별 시작/끝 시각을
계산하므로, 영상 길이를 문장 수로 균등 분할하던 방식보다 훨씬 정확하게 맞습니다.

사용법:
    python narration.py --script output/script.txt --voice ko-KR-SunHiNeural
    (남성 음성: ko-KR-InJoonNeural)
"""
import argparse
import asyncio
import os
import re

import edge_tts

# edge-tts의 offset/duration 단위는 100나노초(틱)입니다.
TICKS_PER_SECOND = 10_000_000

# 자막 한 줄이 너무 길면 화면을 가리므로 이 길이를 넘으면 쪼갭니다.
MAX_CAPTION_CHARS = 45


def clean_script_for_tts(raw_script: str) -> str:
    """[SECTION: ...] 같은 태그를 제거하고 순수 나레이션 텍스트만 추출"""
    return re.sub(r"\[SECTION:.*?\]", "", raw_script).strip()


def split_into_captions(text: str) -> list:
    """문장 단위로 나누고, 너무 긴 문장은 쉼표/공백 기준으로 한 번 더 쪼갠다"""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?？！])\s+", text) if s.strip()]

    captions = []
    for sentence in sentences:
        if len(sentence) <= MAX_CAPTION_CHARS:
            captions.append(sentence)
            continue

        # 쉼표 뒤에서 먼저 끊어보고, 그래도 길면 공백 기준으로 누적해서 끊는다
        pieces = [p.strip() for p in re.split(r"(?<=[,，、])\s*", sentence) if p.strip()]
        buffer = ""
        for piece in pieces:
            for word in piece.split(" ") if len(piece) > MAX_CAPTION_CHARS else [piece]:
                candidate = f"{buffer} {word}".strip()
                if buffer and len(candidate) > MAX_CAPTION_CHARS:
                    captions.append(buffer)
                    buffer = word
                else:
                    buffer = candidate
        if buffer:
            captions.append(buffer)

    return captions


def _visible_len(text: str) -> int:
    """공백을 뺀 글자 수 — WordBoundary 텍스트와 자막 텍스트를 맞추는 기준"""
    return len(re.sub(r"\s+", "", text))


def align_captions(captions: list, boundaries: list) -> list:
    """
    WordBoundary 목록을 자막 문장에 순서대로 배분해서 (시작, 끝, 텍스트)를 만든다.

    boundaries: [(start_sec, end_sec, text), ...] — 발화 순서대로 정렬되어 있음
    """
    captions = [c for c in captions if _visible_len(c) > 0]
    if not captions:
        return []
    if not boundaries:
        return []

    budgets = [_visible_len(c) for c in captions]

    cues = []
    idx = 0
    consumed = 0
    cue_start = boundaries[0][0]
    last_end = boundaries[0][1]

    for start, end, text in boundaries:
        if idx >= len(captions):
            break
        if consumed == 0:
            cue_start = start
        consumed += _visible_len(text)
        last_end = end

        # 한 WordBoundary가 여러 자막에 걸칠 수도 있으므로 while로 소진시킨다
        while idx < len(captions) and consumed >= budgets[idx]:
            cues.append((cue_start, end, captions[idx]))
            consumed -= budgets[idx]
            idx += 1
            cue_start = end

    # 남은 자막은 마지막 시각에 짧게 이어 붙인다 (보통 반올림 오차로 1~2개)
    for leftover in captions[idx:]:
        cues.append((cue_start, max(last_end, cue_start + 1.0), leftover))
        cue_start = max(last_end, cue_start + 1.0)

    # 시작이 끝보다 뒤인 비정상 구간 보정
    return [(s, max(e, s + 0.3), t) for s, e, t in cues]


def format_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(cues: list, path: str):
    lines = []
    for i, (start, end, text) in enumerate(cues, start=1):
        lines.append(str(i))
        lines.append(f"{format_timestamp(start)} --> {format_timestamp(end)}")
        lines.append(text)
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


async def generate_narration(text: str, voice: str, output_path: str, rate: str = "+0%"):
    """음성 파일을 저장하면서 단어 타이밍 정보를 함께 수집한다"""
    communicate = edge_tts.Communicate(text, voice, rate=rate)

    # 먼저 임시 파일에 받고, 끝까지 성공했을 때만 진짜 경로로 옮깁니다.
    # 중간에 네트워크가 끊겨 0바이트짜리 파일이 남으면, 다음 실행에서 그걸
    # "이미 만들어진 나레이션"으로 오해하고 건너뛰게 되기 때문입니다.
    temp_path = output_path + ".part"
    boundaries = []

    try:
        with open(temp_path, "wb") as audio_file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = chunk["offset"] / TICKS_PER_SECOND
                    end = (chunk["offset"] + chunk["duration"]) / TICKS_PER_SECOND
                    boundaries.append((start, end, chunk["text"]))

        if os.path.getsize(temp_path) == 0:
            raise RuntimeError("음성 데이터를 한 바이트도 받지 못했습니다.")
    except BaseException:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

    os.replace(temp_path, output_path)
    return boundaries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", required=True)
    parser.add_argument("--voice", default="ko-KR-SunHiNeural", help="edge-tts --list-voices로 확인")
    parser.add_argument("--rate", default="+0%", help="속도 조절, 예: +10%%, -5%%")
    parser.add_argument("--output", default="output/narration.mp3")
    parser.add_argument(
        "--srt",
        default=None,
        help="자막 파일 경로 (기본값: 음성 파일과 같은 이름의 .srt)",
    )
    args = parser.parse_args()

    with open(args.script, "r", encoding="utf-8") as f:
        raw_script = f.read()

    clean_text = clean_script_for_tts(raw_script)
    if not clean_text:
        raise SystemExit(f"{args.script}에 읽을 내용이 없습니다.")

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    boundaries = asyncio.run(
        generate_narration(clean_text, args.voice, args.output, args.rate)
    )

    srt_path = args.srt or os.path.splitext(args.output)[0] + ".srt"
    captions = split_into_captions(clean_text)
    cues = align_captions(captions, boundaries)

    if cues:
        write_srt(cues, srt_path)
        print(f"완료: {args.output}")
        print(f"자막: {srt_path} ({len(cues)}개 구간, 실제 발화 타이밍 기준)")
        print(f"길이: 약 {cues[-1][1] / 60:.1f}분")
    else:
        print(f"완료: {args.output}")
        print("[경고] 단어 타이밍 정보를 받지 못해 자막 파일을 만들지 못했습니다.")
        print("       영상 합성 단계에서 문장 균등 분할 자막으로 자동 대체됩니다.")

    print(f"글자 수: {len(clean_text)}자")


if __name__ == "__main__":
    main()
