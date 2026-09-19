"""
TTS 음성 + 대본 → 단어별 발화 시각 words.json (타임스탬프를 안 주는 TTS용)

    python tools/align_whisper.py --audio parts/p1/narration.wav --script parts/p1/script.txt --out parts/p1/words.json

faster-whisper로 음성을 인식해 단어 시각을 얻고, 인식 결과와 대본을 함께 저장한다.
인식 텍스트와 대본이 크게 다르면 경고를 낸다 (발음 오류·단어 누락 검수의 1차 근거로도 쓴다).
ElevenLabs의 with-timestamps 응답이나 edge-tts WordBoundary가 있으면 이 도구는 필요 없다.

처음 실행할 때 모델(약 500MB)을 내려받는다. PC에 그래픽카드가 있으면 --device cuda 로 빠르게 돈다.
"""
import argparse
import difflib
import json
import re
from pathlib import Path


def norm(s):
    return re.sub(r"[\s\.,!?…\"'“”‘’「」()\[\]~\-:;·]", "", s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="small", help="tiny/base/small/medium/large-v3")
    ap.add_argument("--device", default="cpu", help="cpu 또는 cuda")
    a = ap.parse_args()

    from faster_whisper import WhisperModel  # 지연 import: 설치 안 된 환경에서 도움말은 보이게

    model = WhisperModel(a.model, device=a.device, compute_type="int8" if a.device == "cpu" else "float16")
    segments, _ = model.transcribe(a.audio, language="ko", word_timestamps=True, vad_filter=True)
    words = []
    for seg in segments:
        for w in seg.words or []:
            words.append({"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)})

    script = Path(a.script).read_text(encoding="utf-8")
    heard = "".join(w["word"] for w in words)
    ratio = difflib.SequenceMatcher(None, norm(script), norm(heard)).ratio()
    Path(a.out).write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(a.out).with_suffix(".heard.txt").write_text(" ".join(w["word"] for w in words), encoding="utf-8")
    print(f"단어 {len(words)}개 → {a.out}")
    print(f"대본-인식 일치율 {ratio:.3f}" + ("" if ratio >= 0.9 else
          "  [경고] 낮습니다. 발음 오류·누락이 있거나 대본과 음성이 다릅니다. .heard.txt를 대본과 대조하세요."))


if __name__ == "__main__":
    main()
