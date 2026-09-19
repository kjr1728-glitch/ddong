"""
나레이션 + 대본 → 단어별 발화 시각 words.json (sherpa-onnx 한국어 zipformer, 오프라인·무료)

    python tools/align_sherpa.py --audio parts/p1/narration.wav --script parts/p1/script.txt \
        --model <sherpa-onnx-zipformer-korean-2024-06-24 폴더> --out parts/p1/words.json

방법
  1. 음성을 무음 지점에서 20~30초 조각으로 나눠 인식 (긴 파일 메모리 문제 회피). 조각 오프셋을 더해 절대 시각으로.
  2. 인식 결과의 글자 스트림(글자, 시각)을 대본 글자 스트림과 difflib로 정렬.
     인식이 틀린 글자는 앞뒤 맞은 글자 사이에서 보간. → 대본의 모든 글자가 시각을 갖는다.
  3. 대본을 어절 단위로 묶어 words.json 출력. build_subs.py가 그대로 읽는다.
  4. 대본-인식 일치율을 출력. 낮으면 발음 오류·누락 검수의 단서.
"""
import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np


def norm_chars(s):
    return re.sub(r"[\s\.,!?…\"'“”‘’「」()\[\]~\-:;·]", "", s)


def read_wav_16k_mono(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def silences(path, noise="-38dB", min_d=0.35):
    log = subprocess.run(["ffmpeg", "-i", str(path), "-af", f"silencedetect=n={noise}:d={min_d}", "-vn", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    s = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
    e = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    return list(zip(s, e))


def chunk_points(total, sil, target=25.0):
    """무음 한가운데를 자르는 지점으로 골라 target초 안팎의 조각을 만든다"""
    cuts, last = [0.0], 0.0
    mids = [(a + b) / 2 for a, b in sil]
    for m in mids:
        if m - last >= target:
            cuts.append(m)
            last = m
    cuts.append(total)
    return cuts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--script", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    import sherpa_onnx
    m = Path(a.model)
    rec = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(m / "encoder-epoch-99-avg-1.int8.onnx"),
        decoder=str(m / "decoder-epoch-99-avg-1.onnx"),
        joiner=str(m / "joiner-epoch-99-avg-1.int8.onnx"),
        tokens=str(m / "tokens.txt"), num_threads=4, sample_rate=16000, feature_dim=80,
        decoding_method="greedy_search")

    samples = read_wav_16k_mono(a.audio)
    total = len(samples) / 16000
    cuts = chunk_points(total, silences(a.audio))
    asr = []  # (char, time)
    for i in range(len(cuts) - 1):
        s0, s1 = cuts[i], cuts[i + 1]
        seg = samples[int(s0 * 16000):int(s1 * 16000)]
        st = rec.create_stream()
        st.accept_waveform(16000, seg)
        rec.decode_stream(st)
        r = st.result
        for tok, t in zip(r.tokens, r.timestamps):
            for ch in norm_chars(tok.replace("▁", " ")):
                asr.append((ch, s0 + float(t)))
        print(f"조각 {i+1}/{len(cuts)-1} {s0:.1f}~{s1:.1f}s: {r.text[:40]}", file=sys.stderr)

    script = Path(a.script).read_text(encoding="utf-8")
    # 대본 글자 스트림 (원문 인덱스 보존)
    s_chars = [(i, ch) for i, ch in enumerate(script) if norm_chars(ch)]
    A = [c for c, _ in asr]
    B = [c for _, c in s_chars]
    sm = difflib.SequenceMatcher(None, A, B, autojunk=False)
    ratio = sm.ratio()
    times = [None] * len(B)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                times[j1 + k] = asr[i1 + k][1]
    # 보간: 시각이 없는 글자는 앞뒤 알려진 시각 사이를 글자 수로 나눔
    known = [i for i, t in enumerate(times) if t is not None]
    if not known:
        sys.exit("인식 결과와 대본이 전혀 맞지 않습니다.")
    first, last = known[0], known[-1]
    for i in range(first):
        times[i] = max(0.0, times[first] - 0.15 * (first - i))
    for i in range(last + 1, len(times)):
        times[i] = min(total, times[last] + 0.15 * (i - last))
    for a0, b0 in zip(known, known[1:]):
        if b0 - a0 > 1:
            for k in range(a0 + 1, b0):
                times[k] = times[a0] + (times[b0] - times[a0]) * (k - a0) / (b0 - a0)
    # 단조 증가 보정
    for i in range(1, len(times)):
        if times[i] < times[i - 1]:
            times[i] = times[i - 1]

    # 어절로 묶기: 원문에서 공백/줄바꿈으로 구분
    words, cur, cur_t = [], "", []
    pos = 0
    idx_to_time = {s_chars[k][0]: times[k] for k in range(len(s_chars))}
    for i, ch in enumerate(script):
        if ch.isspace():
            if cur.strip():
                words.append({"word": cur, "start": round(min(cur_t), 3), "end": round(max(cur_t) + 0.18, 3)})
            cur, cur_t = "", []
        else:
            cur += ch
            if i in idx_to_time:
                cur_t.append(idx_to_time[i])
    if cur.strip() and cur_t:
        words.append({"word": cur, "start": round(min(cur_t), 3), "end": round(max(cur_t) + 0.18, 3)})
    # 끝 시각이 다음 단어 시작을 넘지 않게
    for w1, w2 in zip(words, words[1:]):
        w1["end"] = min(w1["end"], w2["start"]) if w2["start"] > w1["start"] else w1["end"]
    words[-1]["end"] = min(words[-1]["end"], total)

    Path(a.out).write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
    heard = "".join(A)
    Path(a.out).with_suffix(".heard.txt").write_text(heard, encoding="utf-8")
    print(f"단어 {len(words)}개 → {a.out}  (대본-인식 글자 일치율 {ratio:.3f}, 총 {total:.1f}s)")
    if ratio < 0.85:
        print("[경고] 일치율이 낮습니다. .heard.txt를 대본과 대조해 발음 오류·누락을 확인하세요.")


if __name__ == "__main__":
    main()
