"""
ElevenLabs API로 나레이션 생성 (단어별 발화 시각 포함) — voice.json의 보이스 사용

    set ELEVENLABS_API_KEY=...   (또는 story-longform/.env 에 ELEVENLABS_API_KEY=...)
    python tools/tts_elevenlabs.py --script parts/p2/script.txt --out parts/p2

출력: narration.mp3, narration.wav(48kHz 스테레오, +8dB 정규화), words.json, paragraph_times.json
- with-timestamps 엔드포인트가 글자별 시각을 주므로 별도 음성 인식 정렬이 필요 없다.
- 문단(빈 줄) 단위로 나눠 요청하고 이어 붙인다. 문단 사이 쉼 --gap (기본 0.7초).
- speed 1.0, 피치 변경 없음 (규격 15·16번). voice.json의 값을 읽되 speed는 1.0으로 강제.
- 비용: 글자 수만큼 크레딧 (1파트 3,000자 ≈ 3,000 크레딧 ≈ 0.55달러).
"""
import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

TOOLS = Path(__file__).resolve().parent
PROJECT = TOOLS.parent


def load_key():
    k = os.environ.get("ELEVENLABS_API_KEY")
    if k:
        return k
    env = PROJECT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("ELEVENLABS_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    sys.exit("ELEVENLABS_API_KEY가 없습니다. story-longform/.env 에 적어주세요 (elevenlabs.io → 프로필 → API Keys).")


def tts_paragraph(key, voice, text):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice['voice_id']}/with-timestamps"
    body = {
        "text": text,
        "model_id": voice.get("model_id", "eleven_multilingual_v2"),
        "voice_settings": {
            "stability": voice.get("stability", 0.5),
            "similarity_boost": voice.get("similarity_boost", 0.75),
            "style": voice.get("style", 0.0),
            "speed": 1.0,
        },
    }
    r = requests.post(url, json=body, headers={"xi-api-key": key}, timeout=300)
    if r.status_code != 200:
        raise SystemExit(f"ElevenLabs 오류 {r.status_code}: {r.text[:300]}")
    data = r.json()
    audio = base64.b64decode(data["audio_base64"])
    al = data.get("alignment") or data.get("normalized_alignment")
    chars = list(zip(al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]))
    return audio, chars


def duration_of(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def chars_to_words(chars, offset):
    words, cur, s, e = [], "", None, None
    for ch, cs, ce in chars:
        if ch.isspace():
            if cur:
                words.append({"word": cur, "start": round(s + offset, 3), "end": round(e + offset, 3)})
            cur, s, e = "", None, None
        else:
            cur += ch
            s = cs if s is None else s
            e = ce
    if cur:
        words.append({"word": cur, "start": round(s + offset, 3), "end": round(e + offset, 3)})
    return words


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--voice", default=str(PROJECT / "voice.json"))
    ap.add_argument("--gap", type=float, default=0.7)
    ap.add_argument("--gain", default="8dB", help="정규화 게인 (1파트와 동일하게 8dB)")
    a = ap.parse_args()

    key = load_key()
    voice = json.loads(Path(a.voice).read_text(encoding="utf-8"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / "_tts_tmp"
    tmp.mkdir(exist_ok=True)

    text = Path(a.script).read_text(encoding="utf-8")
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    print(f"문단 {len(paras)}개, {len(text)}자 → 약 {len(text)} 크레딧")
    all_words, bounds, pieces, offset = [], [], [], 0.0
    for i, p in enumerate(paras, 1):
        mp3 = tmp / f"{i:03d}.mp3"
        if not mp3.exists():
            audio, chars = tts_paragraph(key, voice, p)
            mp3.write_bytes(audio)
            (tmp / f"{i:03d}.json").write_text(json.dumps(chars, ensure_ascii=False), encoding="utf-8")
        chars = json.loads((tmp / f"{i:03d}.json").read_text(encoding="utf-8"))
        dur = duration_of(mp3)
        all_words += chars_to_words(chars, offset)
        bounds.append({"start": round(offset, 3), "end": round(offset + dur, 3)})
        pieces.append(mp3)
        offset += dur + a.gap
        print(f"문단 {i}/{len(paras)} {dur:.1f}s 누적 {offset:.1f}s")

    silence = tmp / "gap.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{a.gap}", str(silence)], check=True)
    listfile = tmp / "list.txt"
    with listfile.open("w", encoding="utf-8") as f:
        for i, mp3 in enumerate(pieces):
            f.write(f"file '{mp3.name}'\n")
            if i < len(pieces) - 1:
                f.write("file 'gap.wav'\n")
    wav = out / "narration.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
                    "-af", f"volume={a.gain}", "-ar", "48000", "-ac", "2", str(wav)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-b:a", "192k", str(out / "narration.mp3")], check=True)
    total = duration_of(wav)
    bounds[-1]["end"] = round(total, 3)
    (out / "words.json").write_text(json.dumps(all_words, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "paragraph_times.json").write_text(json.dumps(bounds, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"완료: {wav} ({total/60:.1f}분), words.json {len(all_words)}단어, 문단 경계 {len(bounds)}개")


if __name__ == "__main__":
    main()
