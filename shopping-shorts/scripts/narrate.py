"""
3단계: 샷별 나레이션 (edge-tts, 완전 무료)

샷마다 mp3 하나와 단어 타이밍(json)을 만듭니다. 합성 단계에서 클립 길이를
나레이션에 맞추고, 타이밍으로 자막을 정확히 찍기 위해서입니다.

자막 나누기/타이밍 계산은 youtube-automation/scripts/narration.py 의 함수를 그대로 씁니다.

사용법:
    python narrate.py --shotlist shotlist.json --out-dir output/run/narration
"""
import argparse
import asyncio
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "youtube-automation", "scripts"))

from common import load_shotlist  # noqa: E402
from narration import align_captions, generate_narration, split_into_captions  # noqa: E402


def narrate(shotlist_path: str, out_dir: str, voice: str = None, rate: str = "+0%", log=print) -> list:
    data = load_shotlist(shotlist_path)
    voice = voice or data.get("voice", "ko-KR-SunHiNeural")
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for shot in data["shots"]:
        sid = shot["id"]
        text = (shot.get("narration") or "").strip()
        mp3 = os.path.join(out_dir, f"shot_{sid}.mp3")
        meta = os.path.join(out_dir, f"shot_{sid}.json")
        if not text:
            log(f"  [샷 {sid}] 나레이션 없음 (무음)")
            results.append(None)
            continue
        if os.path.exists(mp3) and os.path.getsize(mp3) > 0 and os.path.exists(meta):
            log(f"  [건너뜀] {mp3}")
            results.append(mp3)
            continue
        boundaries = asyncio.run(generate_narration(text, voice, mp3, rate))
        cues = align_captions(split_into_captions(text), boundaries)
        with open(meta, "w", encoding="utf-8") as f:
            json.dump({"text": text, "voice": voice,
                       "cues": [{"start": s, "end": e, "text": t} for s, e, t in cues],
                       "speech_end": boundaries[-1][1] if boundaries else None},
                      f, ensure_ascii=False, indent=2)
        log(f"  [샷 {sid}] {mp3} ({len(text)}자)")
        results.append(mp3)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shotlist", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--voice", default=None, help="기본값은 shotlist의 voice (남성: ko-KR-InJoonNeural)")
    parser.add_argument("--rate", default="+0%")
    args = parser.parse_args()
    out = narrate(args.shotlist, args.out_dir, args.voice, args.rate)
    print(f"완료: 나레이션 {sum(1 for o in out if o)}개 → {args.out_dir}")


if __name__ == "__main__":
    main()
