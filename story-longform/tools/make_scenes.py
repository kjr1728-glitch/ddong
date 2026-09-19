"""
scenes.json 만들기 — 대본 문단(=장면)과 단어 시각으로 장면별 시작/끝 시각을 계산

    python tools/make_scenes.py --script parts/p1/script.txt --words parts/p1/words.json \
        --audio parts/p1/narration.wav --out parts/p1/scenes.json [--images scenes]

- 문단 n의 시작 = 그 문단 첫 단어의 발화 시각 (첫 문단은 0초)
- 문단 n의 끝 = 다음 문단의 시작, 마지막은 나레이션 끝
- 이미지 파일명은 001.png, 002.png … (--images 폴더 기준, scenes.json 위치 상대 경로)
- paragraph_times.json이 같은 폴더에 있으면 그것을 우선 사용 (tts_*.py가 만든 정확한 경계)
"""
import argparse
import json
import re
import subprocess
from pathlib import Path


def norm(s):
    return re.sub(r"[\s\.,!?…\"'“”‘’「」()\[\]~\-:;·]", "", s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--words", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--images", default="scenes")
    ap.add_argument("--ext", default="png")
    a = ap.parse_args()

    total = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", a.audio],
                                 capture_output=True, text=True).stdout.strip())
    paras = [p.strip() for p in Path(a.script).read_text(encoding="utf-8").split("\n\n") if p.strip()]
    pt = Path(a.words).parent / "paragraph_times.json"
    if pt.exists():
        starts = [b["start"] for b in json.loads(pt.read_text(encoding="utf-8"))]
    else:
        words = json.loads(Path(a.words).read_text(encoding="utf-8"))
        # 단어 스트림에서 각 문단의 첫 단어 위치를 글자 누적으로 찾는다
        starts, wi, consumed = [], 0, 0
        for p in paras:
            starts.append(words[wi]["start"] if wi < len(words) else total)
            need = len(norm(p))
            got = 0
            while wi < len(words) and got < need:
                got += len(norm(words[wi]["word"]))
                wi += 1
    starts[0] = 0.0
    scenes = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else total
        scenes.append({"image": f"{a.images}/{i+1:03d}.{a.ext}", "start": round(s, 3), "end": round(e, 3)})
    Path(a.out).write_text(json.dumps(scenes, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"장면 {len(scenes)}개 → {a.out} (총 {total:.1f}s, 평균 {total/len(scenes):.1f}s/장면)")


if __name__ == "__main__":
    main()
