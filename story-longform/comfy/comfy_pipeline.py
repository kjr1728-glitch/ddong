"""
ComfyUI 자동 생성 + 자동 검수 루프 (집 PC, RTX 3070 Ti 8GB)

    # ComfyUI를 먼저 켠다 (run_comfy_8gb.bat) → http://127.0.0.1:8188
    # 1) 인물 기준 얼굴
    python comfy\comfy_pipeline.py refs --prompts works\X\characters\prompts.json --out works\X\characters
    # 2) 장면 (기준 얼굴 참조 → 생성 → 얼굴 검사 → 불합격이면 시드 바꿔 재생성, 최대 --tries 회)
    python comfy\comfy_pipeline.py scenes --prompts works\X\parts\p1\scene_prompts.json ^
        --refs works\X\characters --out works\X\parts\p1\scenes [--only 3,7] [--tries 4]

자동 검사 항목 (규격 6·7·8번의 기계 검사 부분)
  - 얼굴 개수가 등장인물 수와 같은가 (조연·하객은 프롬프트에서 흐림 처리하므로 작은 얼굴은 무시)
  - 각 얼굴이 기준 얼굴과 같은 사람인가 (OpenCV SFace 코사인 유사도 ≥ 0.36)
  - 눈 두 개가 검출되고 기울기가 정상인가 (YuNet 랜드마크)
  - 머리가 프레임 가장자리에 붙어 잘리지 않았는가
  통과한 이미지만 NNN.png로 저장하고, 모든 시도의 점수를 qc_images.json에 남긴다.
  손가락·동공 세부 오류는 기계로 못 잡으므로 Claude Code가 이미지를 열어 2차 검사한다.

두 명 이상 장면: 기준 얼굴들을 가로로 이어 붙인 한 장을 참조로 넣는다 (Kontext는 참조 1장).
"""
import argparse
import io
import json
import random
import sys
import time
import uuid
from pathlib import Path

import numpy as np
import requests
from PIL import Image

HERE = Path(__file__).resolve().parent
COMFY_URL = "http://127.0.0.1:8188"
FACE_DIR = None  # 설치 스크립트가 만든 face_models 폴더 (자동 탐색)

PRE = ("Photorealistic still from a Korean TV drama, shot on a cinema camera, natural skin texture with pores, "
       "soft realistic lighting, true-to-life colors, no beauty filter, no illustration, no anime, no CGI look, "
       "no text, no watermark.")
FRAME = "Wide 16:9 cinematic frame with generous headroom; full head and hands inside the frame."


# ---------------- ComfyUI API ----------------
def comfy_upload(path):
    with open(path, "rb") as f:
        r = requests.post(f"{COMFY_URL}/upload/image", files={"image": (Path(path).name, f, "image/png")},
                          data={"overwrite": "true"}, timeout=60)
    r.raise_for_status()
    return r.json()["name"]


def comfy_run(workflow, timeout=900):
    cid = str(uuid.uuid4())
    r = requests.post(f"{COMFY_URL}/prompt", json={"prompt": workflow, "client_id": cid}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"ComfyUI 거부: {r.text[:500]}")
    pid = r.json()["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = requests.get(f"{COMFY_URL}/history/{pid}", timeout=30).json()
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                raise RuntimeError("ComfyUI 실행 오류: " + json.dumps(st, ensure_ascii=False)[:500])
            for node in h[pid]["outputs"].values():
                for im in node.get("images", []):
                    q = {"filename": im["filename"], "subfolder": im.get("subfolder", ""), "type": im.get("type", "output")}
                    return requests.get(f"{COMFY_URL}/view", params=q, timeout=120).content
        time.sleep(2)
    raise TimeoutError("ComfyUI 응답 없음")


def load_wf(name):
    return json.loads((HERE / "workflows" / name).read_text(encoding="utf-8"))


# ---------------- 얼굴 검사 (OpenCV YuNet + SFace) ----------------
class FaceQC:
    def __init__(self):
        import cv2
        global FACE_DIR
        for cand in [HERE / "face_models", Path("D:/ComfyUI/face_models"), Path("C:/ComfyUI/face_models")]:
            if (cand / "yunet.onnx").exists():
                FACE_DIR = cand
                break
        if FACE_DIR is None:
            raise SystemExit("face_models 폴더(yunet.onnx, sface.onnx)를 못 찾았습니다. install_comfyui.ps1을 먼저 실행하세요.")
        self.cv2 = cv2
        self.det = cv2.FaceDetectorYN.create(str(FACE_DIR / "yunet.onnx"), "", (320, 320), 0.7, 0.3, 5000)
        self.rec = cv2.FaceRecognizerSF.create(str(FACE_DIR / "sface.onnx"), "")

    def faces(self, img_bgr, min_frac=0.06):
        h, w = img_bgr.shape[:2]
        self.det.setInputSize((w, h))
        _, f = self.det.detect(img_bgr)
        out = []
        if f is None:
            return out
        for row in f:
            x, y, bw, bh = row[:4]
            if bw < w * min_frac:  # 작은 배경 얼굴은 무시
                continue
            out.append(row)
        return sorted(out, key=lambda r: -r[2] * r[3])

    def embed(self, img_bgr, row):
        aligned = self.rec.alignCrop(img_bgr, row)
        return self.rec.feature(aligned)

    def sim(self, e1, e2):
        return float(self.rec.match(e1, e2, self.cv2.FaceRecognizerSF_FR_COSINE))

    def check(self, img_path, ref_embeds, expected):
        """반환: (통과여부, 사유 목록, 점수 dict)"""
        cv2 = self.cv2
        img = cv2.imread(str(img_path))
        h, w = img.shape[:2]
        fs = self.faces(img)
        reasons, scores = [], {"faces": len(fs), "sims": []}
        if expected and len(fs) < expected:
            reasons.append(f"얼굴 {len(fs)}개 (기대 {expected})")
        if expected and len(fs) > expected + 1:
            reasons.append(f"얼굴이 너무 많음 {len(fs)}개")
        for row in fs[:max(expected, 1)]:
            x, y, bw, bh = row[:4]
            # 잘림: 얼굴 박스가 가장자리 2% 안에 붙으면 머리 잘림 의심
            if y < h * 0.02 or x < w * 0.02 or x + bw > w * 0.98:
                reasons.append("얼굴이 프레임 가장자리에 붙음(잘림 의심)")
            # 눈: 랜드마크 4~7 = 오른눈, 왼눈 (x,y)
            rx, ry, lx, ly = row[4], row[5], row[6], row[7]
            ang = abs(np.degrees(np.arctan2(ly - ry, lx - rx)))
            if ang > 25:
                reasons.append(f"눈 기울기 {ang:.0f}도")
            if abs(lx - rx) < bw * 0.2:
                reasons.append("두 눈 간격 비정상")
        # 동일 인물: 각 기대 인물이 어떤 얼굴과든 유사도 기준을 넘어야 함
        embeds = [self.embed(img, row) for row in fs]
        for name, ref in ref_embeds.items():
            best = max((self.sim(ref, e) for e in embeds), default=0.0)
            scores["sims"].append({name: round(best, 3)})
            if best < 0.36:
                reasons.append(f"{name} 얼굴 불일치 (유사도 {best:.2f})")
        return (not reasons), reasons, scores


# ---------------- 실행 ----------------
def run_refs(a):
    prompts = json.loads(Path(a.prompts).read_text(encoding="utf-8"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, desc in prompts.items():
        dst = out / f"ref_{name}.png"
        if dst.exists() and not a.force:
            print("있음:", dst.name)
            continue
        wf = load_wf("ref_portrait.json")
        wf["7"]["inputs"]["text"] = (f"{PRE} Character reference portrait, upper body, three-quarter angle facing camera, "
                                     f"neutral expression, blurred plain indoor background. {desc}")
        wf["12"]["inputs"]["seed"] = random.randint(1, 2**31)
        t0 = time.time()
        dst.write_bytes(comfy_run(wf))
        print(f"생성: {dst.name} ({time.time()-t0:.0f}s)")
    print("기준 얼굴을 눈으로 확인하고, 마음에 안 드는 인물은 파일을 지우고 다시 실행하세요.")


def stitched_ref(ref_paths, tmp):
    ims = [Image.open(p).convert("RGB") for p in ref_paths]
    h = min(im.height for im in ims)
    ims = [im.resize((int(im.width * h / im.height), h)) for im in ims]
    canvas = Image.new("RGB", (sum(im.width for im in ims), h), "white")
    x = 0
    for im in ims:
        canvas.paste(im, (x, 0))
        x += im.width
    p = tmp / ("stitch_" + "_".join(Path(r).stem for r in ref_paths) + ".png")
    canvas.save(p)
    return p


def run_scenes(a):
    scenes = json.loads(Path(a.prompts).read_text(encoding="utf-8"))
    refs, out = Path(a.refs), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / "_tries"
    tmp.mkdir(exist_ok=True)
    only = {int(x) for x in a.only.split(",")} if a.only else None
    qc = FaceQC()
    ref_embed_cache = {}

    def ref_embed(name):
        if name not in ref_embed_cache:
            img = qc.cv2.imread(str(refs / f"ref_{name}.png"))
            fs = qc.faces(img, min_frac=0.0)
            if not fs:
                raise SystemExit(f"기준 얼굴에서 얼굴을 못 찾음: ref_{name}.png")
            ref_embed_cache[name] = qc.embed(img, fs[0])
        return ref_embed_cache[name]

    log_path = out / "qc_images.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    for s in scenes:
        n = s["n"]
        if only and n not in only:
            continue
        dst = out / f"{n:03d}.png"
        if dst.exists() and not a.force:
            print("있음:", dst.name)
            continue
        who = s.get("who", [])
        prompt = s["prompt"]
        for i, w in enumerate(who):
            prompt = prompt.replace("{" + w + "}", f"the person from the reference image{' (left)' if len(who) > 1 and i == 0 else ' (right)' if len(who) > 1 else ''} ({w}), same face, same hair, same age")
        text = f"{PRE} {FRAME} {prompt}"
        wf = load_wf("scene_kontext.json")
        if who:
            ref_paths = [refs / f"ref_{w}.png" for w in who]
            ref_img = ref_paths[0] if len(who) == 1 else stitched_ref(ref_paths, tmp)
            wf["4"]["inputs"]["image"] = comfy_upload(ref_img)
            text = ("Keep the exact face identity from the reference image for each named person; "
                    "change setting, pose, clothing and framing as described. " + text)
        else:
            # 참조 없는 장면(사물·풍경): 참조 노드를 떼고 일반 생성
            for k in ("4", "5", "6", "8"):
                wf.pop(k, None)
            wf["9"]["inputs"]["conditioning"] = ["7", 0]
            wf["9"]["inputs"]["guidance"] = 3.0
        wf["7"]["inputs"]["text"] = text
        ref_embeds = {w: ref_embed(w) for w in who}
        passed = False
        for t in range(1, a.tries + 1):
            wf["12"]["inputs"]["seed"] = random.randint(1, 2**31)
            t0 = time.time()
            try:
                png = comfy_run(wf)
            except Exception as e:  # noqa: BLE001
                print(f"장면 {n} 시도 {t}: ComfyUI 오류 {e}")
                continue
            trial = tmp / f"{n:03d}_try{t}.png"
            trial.write_bytes(png)
            ok, reasons, scores = qc.check(trial, ref_embeds, len(who))
            log.setdefault(str(n), []).append({"try": t, "ok": ok, "reasons": reasons, **scores, "seed": wf["12"]["inputs"]["seed"]})
            log_path.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"장면 {n} 시도 {t} ({time.time()-t0:.0f}s): {'통과' if ok else '불합격 ' + ', '.join(reasons)}")
            if ok:
                dst.write_bytes(png)
                passed = True
                break
        if not passed:
            print(f"장면 {n}: {a.tries}회 모두 불합격. _tries 폴더의 후보를 사람이 고르거나 프롬프트를 바꾸세요.")
    print("완료. qc_images.json에 시도별 점수가 있습니다. 통과 이미지도 Claude Code로 눈·손 2차 검사를 받으세요.")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("refs")
    r.add_argument("--prompts", required=True)
    r.add_argument("--out", required=True)
    s = sub.add_parser("scenes")
    s.add_argument("--prompts", required=True)
    s.add_argument("--refs", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--only")
    s.add_argument("--tries", type=int, default=4)
    for p in (r, s):
        p.add_argument("--force", action="store_true")
        p.add_argument("--url", default=COMFY_URL)
    a = ap.parse_args()
    global COMFY_URL
    COMFY_URL = a.url
    try:
        requests.get(f"{COMFY_URL}/system_stats", timeout=5)
    except Exception:  # noqa: BLE001
        sys.exit("ComfyUI에 연결할 수 없습니다. run_comfy_8gb.bat 를 먼저 실행하세요.")
    (run_refs if a.cmd == "refs" else run_scenes)(a)


if __name__ == "__main__":
    main()
