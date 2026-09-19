"""
Gemini API(무료 등급)로 장면 이미지 자동 생성 — 인물 기준 얼굴을 참조 이미지로 넣어 일관성 유지

    # 1) 인물 기준 얼굴 (텍스트만, 3:4)
    python tools/gen_images_gemini.py refs --prompts works/X/characters/prompts.json --out works/X/characters
    # 2) 장면 (기준 얼굴 참조, 16:9)
    python tools/gen_images_gemini.py scenes --prompts works/X/parts/p1/scene_prompts.json \
        --refs works/X/characters --out works/X/parts/p1/scenes [--only 3,7,12]

API 키: 환경변수 GEMINI_API_KEY 또는 story-longform/.env 의 GEMINI_API_KEY=... (저장소에 올리지 않음)
모델: --model 기본 gemini-2.5-flash-image. 실패하면 --model gemini-3.1-flash-image-preview 등으로 바꿔 시도.
무료 등급 한도(분당/일일)에 걸리면 429가 오므로 대기 후 재시도한다.
"""
import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

import requests

TOOLS = Path(__file__).resolve().parent
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

PRE = ("Photorealistic still from a Korean TV drama, shot on a cinema camera, natural skin texture with pores, "
       "soft realistic lighting, true-to-life colors, no beauty filter, no illustration, no anime, no CGI look, "
       "no text, no watermark, no captions.")
FRAME = "16:9 widescreen frame. Keep generous headroom: full head and hands inside the frame, nothing cropped."


def load_key():
    k = os.environ.get("GEMINI_API_KEY")
    if k:
        return k
    env = TOOLS.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    sys.exit("GEMINI_API_KEY가 없습니다. story-longform/.env 에 GEMINI_API_KEY=... 를 적어주세요.")


def img_part(path):
    p = Path(path)
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return {"inline_data": {"mime_type": mime, "data": base64.b64encode(p.read_bytes()).decode()}}


def generate(key, model, parts, aspect, retries=6):
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}},
    }
    url = API.format(model=model, key=key)
    for attempt in range(retries):
        r = requests.post(url, json=body, timeout=180)
        if r.status_code == 200:
            data = r.json()
            for cand in data.get("candidates", []):
                for part in cand.get("content", {}).get("parts", []):
                    if "inlineData" in part:
                        return base64.b64decode(part["inlineData"]["data"]), None
            return None, f"이미지 없음: {json.dumps(data, ensure_ascii=False)[:300]}"
        if r.status_code in (429, 500, 503):
            wait = min(60, 5 * (attempt + 1))
            msg = r.text[:200].replace("\n", " ")
            print(f"  {r.status_code} → {wait}s 대기 후 재시도 ({msg})", file=sys.stderr)
            time.sleep(wait)
            continue
        if r.status_code == 400 and "imageConfig" in r.text:
            # 구형 모델: aspectRatio 미지원 → 설정 빼고 재시도
            body["generationConfig"].pop("imageConfig", None)
            continue
        return None, f"HTTP {r.status_code}: {r.text[:300]}"
    return None, "재시도 초과"


def run_refs(a, key):
    prompts = json.loads(Path(a.prompts).read_text(encoding="utf-8"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, desc in prompts.items():
        dst = out / f"ref_{name}.png"
        if dst.exists() and not a.force:
            print(f"있음: {dst.name}")
            continue
        text = (f"{PRE} Character reference portrait, upper body, three-quarter angle facing camera, "
                f"neutral expression, blurred plain indoor background. {desc}")
        img, err = generate(key, a.model, [{"text": text}], "3:4")
        if img:
            dst.write_bytes(img)
            print(f"생성: {dst.name} ({len(img)//1024} KB)")
        else:
            print(f"실패: {name} — {err}")
        time.sleep(a.sleep)


def run_scenes(a, key):
    scenes = json.loads(Path(a.prompts).read_text(encoding="utf-8"))
    refs = Path(a.refs)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    only = {int(x) for x in a.only.split(",")} if a.only else None
    for s in scenes:
        n = s["n"]
        if only and n not in only:
            continue
        dst = out / f"{n:03d}.png"
        if dst.exists() and not a.force:
            print(f"있음: {dst.name}")
            continue
        parts = []
        prompt = s["prompt"]
        for i, who in enumerate(s.get("who", [])):
            ref = refs / f"ref_{who}.png"
            if not ref.exists():
                print(f"실패: 장면 {n} — 기준 얼굴 없음 {ref}")
                break
            parts.append(img_part(ref))
            tag = f"the person in reference image {i+1} ({who}), same face, same hair, same age"
            prompt = prompt.replace("{" + who + "}", tag)
        else:
            text = f"{PRE} {FRAME} Use the attached reference images strictly for each named person's face. Scene: {prompt}"
            parts.append({"text": text})
            img, err = generate(key, a.model, parts, "16:9")
            if img:
                dst.write_bytes(img)
                print(f"생성: {dst.name} ({len(img)//1024} KB)")
            else:
                print(f"실패: 장면 {n} — {err}")
            time.sleep(a.sleep)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("refs")
    r.add_argument("--prompts", required=True, help='{"서윤": "설명", ...} JSON')
    r.add_argument("--out", required=True)
    s = sub.add_parser("scenes")
    s.add_argument("--prompts", required=True, help="scene_prompts.json")
    s.add_argument("--refs", required=True, help="ref_이름.png 폴더")
    s.add_argument("--out", required=True)
    s.add_argument("--only", help="장면 번호 콤마 구분 (재생성용)")
    for p in (r, s):
        p.add_argument("--model", default="gemini-2.5-flash-image")
        p.add_argument("--sleep", type=float, default=6.0, help="요청 간격(초). 무료 등급 분당 한도 대비")
        p.add_argument("--force", action="store_true", help="이미 있는 파일도 다시 생성")
    a = ap.parse_args()
    key = load_key()
    (run_refs if a.cmd == "refs" else run_scenes)(a, key)


if __name__ == "__main__":
    main()
