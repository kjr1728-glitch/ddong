"""
6파트 → 최종 합본 (재인코딩 없이 스트림 복사, faststart)

    python tools/concat_parts.py --parts parts/p1/part1.mp4 parts/p2/part2.mp4 ... --out final/final.mp4

모든 파트가 같은 규격(render_part.py 출력)이어야 한다. 규격이 다르면 멈춘다.
"""
import argparse
import subprocess
from pathlib import Path


def probe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name,width,height,r_frame_rate,pix_fmt",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, encoding="utf-8")
    return r.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    parts = [Path(p).resolve() for p in a.parts]
    sigs = {p: probe(p) for p in parts}
    if len(set(sigs.values())) != 1:
        lines = "\n".join(f"  {p.name}: {s}" for p, s in sigs.items())
        raise SystemExit("파트 규격이 서로 다릅니다:\n" + lines)

    out = Path(a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    listfile = out.with_suffix(".list.txt")
    with listfile.open("w", encoding="utf-8") as f:
        for p in parts:
            f.write("file '" + str(p).replace("\\", "/").replace("'", r"'\''") + "'\n")

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stats",
           "-f", "concat", "-safe", "0", "-i", str(listfile),
           "-c", "copy", "-movflags", "+faststart", str(out)]
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit("합본 실패")
    print("완료:", out)


if __name__ == "__main__":
    main()
