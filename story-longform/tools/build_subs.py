"""
대본 + 단어별 발화 시각 → 규격 ASS 자막 (SRT도 함께)

입력
  --script  파트 대본 (.txt). 한 줄에 한 문장이 아니어도 된다. 문장 단위로 자동 분리.
  --words   단어별 타이밍 JSON: [{"word": "...", "start": 초, "end": 초}, ...]
            edge-tts WordBoundary, ElevenLabs alignment, align_whisper.py 출력 모두 이 형식으로 맞춘다.
출력
  --out     .ass 경로 (같은 이름의 .srt도 같이 만든다)

줄바꿈 원칙 (규격 12번)
  - 한 줄 최대 26자, 최대 2줄. 단어 중간에서 자르지 않는다 (공백에서만 나눈다).
  - 2줄이 필요하면 문장 부호 뒤 > 연결어미/조사로 끝나는 어절 뒤 > 그 외 순으로,
    가운데에 가장 가까운 지점에서 나눈다.
  - 둘째 줄이 한 어절이나 4자 미만이면 그 지점은 쓰지 않는다.
  - 2줄에도 안 들어가는 긴 문장은 절 단위로 여러 자막으로 나누고 각각 타이밍을 준다.

타이밍 원칙 (규격 13번)
  - 시작 = 그 자막 첫 글자의 발화 시각, 끝 = 마지막 글자 발화 종료 + SUB_TAIL_SEC.
  - 끝은 다음 자막 시작을 절대 넘지 않는다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spec import ASS_HEADER, MAX_CHARS_PER_LINE, MAX_LINES, SUB_TAIL_SEC  # noqa: E402

SENT_END = re.compile(r"(?<=[.!?…」”\"])\s+|\n+")
CLAUSE_END_PUNCT = ("," , "、", ";", ":", "…")
# 어절 끝이 이 글자면 "의미 단위 경계"로 본다 (연결어미·조사)
BOUNDARY_TAILS = (
    "고", "며", "면", "서", "데", "만", "도", "은", "는", "이", "가", "을", "를",
    "에", "로", "와", "과", "께", "의", "요", "지", "듯", "뒤", "후", "때",
)


def norm(s: str) -> str:
    """타이밍 매칭용: 공백·문장부호 제거"""
    return re.sub(r"[\s\.,!?…\"'“”‘’「」()\[\]~\-:;·]", "", s)


def split_sentences(text: str):
    parts = [p.strip() for p in SENT_END.split(text) if p and p.strip()]
    return parts


def boundary_score(word: str) -> int:
    if word.endswith(CLAUSE_END_PUNCT):
        return 3
    if word[-1] in BOUNDARY_TAILS:
        return 2
    return 1


def best_split(words, max_len=MAX_CHARS_PER_LINE):
    """어절 목록을 두 줄로 나눌 최적 인덱스 반환 (없으면 None)"""
    n = len(words)
    total = len(" ".join(words))
    best = None
    for i in range(1, n):
        l1 = " ".join(words[:i])
        l2 = " ".join(words[i:])
        if len(l1) > max_len or len(l2) > max_len:
            continue
        if len(words[i:]) < 2 and len(l2) < 4:
            continue  # 조사·한 글자만 다음 줄로 넘어가는 것 금지
        score = boundary_score(words[i - 1])
        balance = abs(len(l1) - len(l2)) / max(total, 1)
        key = (score, -balance)
        if best is None or key > best[0]:
            best = (key, i)
    return None if best is None else best[1]


def chunk_sentence(sentence: str):
    """문장 → 자막 큐 텍스트 목록 (각 큐는 1~2줄, 줄은 \\N 으로 구분)"""
    words = sentence.split()
    if not words:
        return []
    if len(sentence) <= MAX_CHARS_PER_LINE:
        return [sentence]
    if len(sentence) <= MAX_CHARS_PER_LINE * MAX_LINES:
        i = best_split(words)
        if i is not None:
            return [" ".join(words[:i]) + r"\N" + " ".join(words[i:])]
    # 2줄에도 안 들어가면 절 단위로 앞에서부터 잘라 여러 큐로
    cues, cur = [], []
    for w in words:
        trial = " ".join(cur + [w])
        if len(trial) > MAX_CHARS_PER_LINE * MAX_LINES - 6 and cur:
            cues.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
        # 절 경계(부호)에서 넉넉히 끊어 두는 편이 읽기 좋다
        if cur and cur[-1].endswith(CLAUSE_END_PUNCT) and len(" ".join(cur)) >= MAX_CHARS_PER_LINE:
            cues.append(" ".join(cur))
            cur = []
    if cur:
        cues.append(" ".join(cur))
    out = []
    for c in cues:
        out.extend(chunk_sentence(c) if len(c) > MAX_CHARS_PER_LINE else [c])
    return out


def build_char_stream(words):
    """단어 타이밍 → 글자 단위 (char, start, end) 스트림"""
    stream = []
    for w in words:
        chars = norm(w["word"])
        if not chars:
            continue
        s, e = float(w["start"]), float(w["end"])
        step = (e - s) / len(chars)
        for k, ch in enumerate(chars):
            stream.append((ch, s + step * k, s + step * (k + 1)))
    return stream


def assign_timing(cues, stream):
    """큐 순서대로 글자 스트림을 소비하며 시작/끝 시각 부여"""
    pos = 0
    timed = []
    total_chars = len(stream)
    for text in cues:
        n = len(norm(text.replace(r"\N", " ")))
        if n == 0:
            continue
        if pos >= total_chars:
            raise SystemExit(
                "타이밍 데이터가 대본보다 짧습니다. 대본과 TTS 입력 텍스트가 같은지 확인하세요."
            )
        end_idx = min(pos + n, total_chars) - 1
        start = stream[pos][1]
        end = stream[end_idx][2]
        timed.append([start, end, text])
        pos = end_idx + 1
    leftover = total_chars - pos
    if abs(leftover) > max(10, total_chars * 0.03):
        print(f"[경고] 대본과 타이밍 글자 수 차이가 큽니다 (남은 글자 {leftover}). "
              "대본/TTS 텍스트 불일치 또는 인식 오류를 확인하세요.", file=sys.stderr)
    # 끝 시각: 여유를 주되 다음 큐 시작을 넘지 않게
    for i, cue in enumerate(timed):
        cue[1] += SUB_TAIL_SEC
        if i + 1 < len(timed):
            cue[1] = min(cue[1], timed[i + 1][0])
        if cue[1] <= cue[0]:
            cue[1] = cue[0] + 0.05
    return timed


def ass_time(t: float) -> str:
    cs = int(round(t * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, c = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--words", required=True)
    ap.add_argument("--out", required=True, help=".ass 출력 경로")
    a = ap.parse_args()

    text = Path(a.script).read_text(encoding="utf-8")
    words = json.loads(Path(a.words).read_text(encoding="utf-8"))
    cues = []
    for s in split_sentences(text):
        cues.extend(chunk_sentence(s))
    timed = assign_timing(cues, build_char_stream(words))

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig") as f:
        f.write(ASS_HEADER)
        for s, e, t in timed:
            f.write(f"Dialogue: 0,{ass_time(s)},{ass_time(e)},Default,,0,0,0,,{t}\n")
    with out.with_suffix(".srt").open("w", encoding="utf-8") as f:
        for i, (s, e, t) in enumerate(timed, 1):
            f.write(f"{i}\n{srt_time(s)} --> {srt_time(e)}\n{t.replace(chr(92)+'N', chr(10))}\n\n")

    longest = max(timed, key=lambda c: len(c[2]))
    two_line = sum(1 for c in timed if r"\N" in c[2])
    print(f"자막 {len(timed)}개 (2줄 {two_line}개) → {out}")
    print(f"  첫 자막  {ass_time(timed[0][0])} ~ {ass_time(timed[0][1])}  {timed[0][2]}")
    print(f"  마지막   {ass_time(timed[-1][0])} ~ {ass_time(timed[-1][1])}  {timed[-1][2]}")
    print(f"  가장 긴  {ass_time(longest[0])} ~ {ass_time(longest[1])}  {longest[2]}")


if __name__ == "__main__":
    main()
