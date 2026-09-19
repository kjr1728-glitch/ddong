"""
무료 TTS (edge-tts, Microsoft Edge 음성) — 대본 → narration.mp3 + words.json

    pip install edge-tts
    python tools/tts_edge.py --script parts/p1/script.txt --out parts/p1 --voice ko-KR-SunHiNeural

- 가입·API 키 없이 무료. 단어별 발화 시각(words.json)을 같이 준다 → build_subs.py에 바로 씀.
- 한국어 여성 보이스는 ko-KR-SunHiNeural 하나 (남성: ko-KR-InJoonNeural, ko-KR-HyunsuMultilingualNeural).
- rate/pitch 기본값 0. 규격 15·16번(피치 변경 금지, 무단 배속 금지)에 따라 바꾸지 않는다.
- 문단 단위로 나눠 합성한 뒤 이어 붙인다 (긴 텍스트 한 번에 보내면 끊기는 일이 있음).
  문단 사이 쉼은 --gap 초 (기본 0.6).

집 PC에서 실행한다. (클라우드 세션은 이 서비스 접속이 차단돼 있음)
"""
import argparse
import asyncio
import json
import subprocess
from pathlib import Path


async def synth_paragraph(text, voice, mp3_path):
    import edge_tts
    words = []
    c = edge_tts.Communicate(text, voice)
    with open(mp3_path, "wb") as f:
        async for ch in c.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append({"word": ch["text"], "start": ch["offset"] / 1e7,
                              "end": (ch["offset"] + ch["duration"]) / 1e7})
    return words


def duration_of(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(r.stdout.strip())


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", required=True, help="출력 폴더 (narration.mp3, narration.wav, words.json)")
    ap.add_argument("--voice", default="ko-KR-SunHiNeural")
    ap.add_argument("--gap", type=float, default=0.6, help="문단 사이 쉼(초)")
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / "_tts_tmp"
    tmp.mkdir(exist_ok=True)

    text = Path(a.script).read_text(encoding="utf-8")
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    all_words, offset, pieces = [], 0.0, []
    for i, p in enumerate(paras, 1):
        mp3 = tmp / f"{i:03d}.mp3"
        words = await synth_paragraph(p, a.voice, mp3)
        dur = duration_of(mp3)
        for w in words:
            all_words.append({"word": w["word"], "start": round(w["start"] + offset, 3),
                              "end": round(w["end"] + offset, 3)})
        pieces.append((mp3, dur))
        offset += dur + a.gap
        print(f"문단 {i}/{len(paras)}  {dur:.1f}s  누적 {offset:.1f}s")

    # 이어 붙이기: 문단 사이에 무음 gap 삽입
    listfile = tmp / "list.txt"
    silence = tmp / "gap.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                    "-t", f"{a.gap}", str(silence)], check=True)
    with listfile.open("w", encoding="utf-8") as f:
        for i, (mp3, _) in enumerate(pieces):
            f.write(f"file '{mp3.name}'\n")
            if i < len(pieces) - 1:
                f.write("file 'gap.wav'\n")
    wav = out / "narration.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
                    "-ar", "48000", "-ac", "2", str(wav)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-b:a", "192k", str(out / "narration.mp3")], check=True)
    (out / "words.json").write_text(json.dumps(all_words, ensure_ascii=False, indent=1), encoding="utf-8")
    # 장면 경계(문단 끝 시각)도 같이 저장 → scenes.json 만들 때 사용
    bounds, t = [], 0.0
    for mp3, dur in pieces:
        bounds.append({"start": round(t, 3), "end": round(t + dur, 3)})
        t += dur + a.gap
    bounds[-1]["end"] = round(duration_of(wav), 3)
    (out / "paragraph_times.json").write_text(json.dumps(bounds, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"완료: {wav} ({duration_of(wav):.1f}s), words.json {len(all_words)}단어, 문단 경계 {len(bounds)}개")


if __name__ == "__main__":
    asyncio.run(main())
