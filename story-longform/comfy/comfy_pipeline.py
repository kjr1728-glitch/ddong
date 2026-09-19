r"""
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
import hashlib
import io
import json
import random
import re
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

# 장면 공통 접두어. 기준 얼굴과 같은 질감(부드러운 조명·저대비·깨끗하지만 실제 같은 피부)으로 맞춘다.
# 부정형("no CGI", "no text")은 FLUX가 오히려 그리므로 쓰지 않는다.
PRE = ("Photorealistic still frame from a Korean TV drama, a real photograph, soft natural realistic lighting, "
       "low contrast, neutral color grading, true-to-life colors, clean realistic skin with subtle natural texture.")
# 기준 얼굴 전용 스타일 (사용자 견본: 한국 드라마 캐스팅 프로필 — 밝은 회색 단색 배경, 부드러운 정면 조명,
# 저대비, 깨끗하지만 실제 같은 피부, 절제된 주름, 차분한 표정, 머리 주변 여백).
# FLUX는 부정형("no makeup")을 오히려 그리므로 긍정형으로만 쓴다. 다큐·거친 질감 표현은 주름과 그림자를 과장하므로 뺀다.
REF_STYLE = ("Professional studio headshot, head and upper shoulders, hands out of frame, camera at eye level, "
             "natural camera distance with comfortable space around the head, the subject fills about 70 percent of "
             "the frame. Plain medium-light neutral grey solid seamless background. Soft even frontal studio lighting from a large "
             "softbox, very soft shadows, low contrast, neutral color grading, soft warm-neutral Korean skin tone. "
             "Clean realistic skin with subtle natural texture, gentle age-appropriate lines, natural lip color. "
             "Calm, serious, restrained expression with a relaxed brow. Polished commercial casting portrait, 85mm lens.")
FRAME = ("Wide 16:9 frame with generous headroom; full head and hands inside the frame. Set in present-day South Korea "
         "with Korean interiors and Korean people. Candid unposed story moment: people look at each other or at what "
         "they are doing, never at the camera.")


# ---------------- ComfyUI API ----------------
def comfy_upload(path):
    # 한글 파일명은 멀티파트 헤더에서 깨질 수 있어 ASCII 이름으로 올린다
    safe = "ref_" + hashlib.md5(Path(path).name.encode("utf-8")).hexdigest()[:12] + ".png"
    with open(path, "rb") as f:
        r = requests.post(f"{COMFY_URL}/upload/image", files={"image": (safe, f, "image/png")},
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
def imread_u(path):
    """cv2.imread는 Windows에서 한글 경로를 못 읽으므로 바이트로 읽어 디코드한다."""
    import cv2
    img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit(f"이미지를 읽을 수 없음: {path}")
    return img



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
        img = imread_u(img_path)
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
    only = set(a.only.split(",")) if a.only else None
    cand_dir = out / "_candidates"
    if a.n > 1:
        cand_dir.mkdir(exist_ok=True)
    for name, desc in prompts.items():
        if only and name not in only:
            continue
        # 기준 얼굴에는 손·손목이 나오지 않게 한다: 손목 흉터·손 자세 문구는 장면 프롬프트가 담당
        # (그대로 두면 흉터를 보여주려고 손을 들어 올리거나 문신처럼 그린다)
        face_desc = re.sub(r",\s*(hands folded|arms crossed)", "", desc)
        face_desc = " ".join(s for s in re.split(r"(?<=[.])\s+", face_desc) if not re.search(r"wrist", s, re.I))
        # 인물 묘사를 맨 앞에 둔다 (뒤에 두면 머리 모양·옷·체형이 잘 반영되지 않음)
        text = f"Korean drama casting reference photo of a {face_desc} {REF_STYLE}"
        targets = [out / f"ref_{name}.png"] if a.n == 1 else [cand_dir / f"{name}{a.tag}_{i}.png" for i in range(1, a.n + 1)]
        for dst in targets:
            if dst.exists() and not a.force:
                print("있음:", dst.name)
                continue
            wf = load_wf("ref_portrait.json")
            wf["7"]["inputs"]["text"] = text
            wf["9"]["inputs"]["guidance"] = a.guidance  # 높을수록 매끈한 AI 피부가 된다
            if a.lora:  # 리얼리즘 LoRA: GGUF 로더와 샘플러 사이에 끼운다. 사진다움만 보태는 용도로 약하게
                # (0.9 + 트리거 단어는 주름·그림자·거친 피부를 과장해서 사용자가 반려함)
                wf["20"] = {"class_type": "LoraLoaderModelOnly",
                            "inputs": {"model": ["1", 0], "lora_name": a.lora, "strength_model": a.lora_strength}}
                wf["12"]["inputs"]["model"] = ["20", 0]
            wf["11"]["inputs"].update(width=1024, height=1024)
            wf["12"]["inputs"]["seed"] = random.randint(1, 2**31)
            t0 = time.time()
            dst.write_bytes(comfy_run(wf))
            print(f"생성: {dst.name} ({time.time()-t0:.0f}s)", flush=True)
    if a.n > 1:
        print("후보 중 하나를 골라 ref_이름.png 로 복사하세요:", cand_dir)
    print("기준 얼굴을 눈으로 확인하고, 마음에 안 드는 인물은 파일을 지우고 다시 실행하세요.")


def head_crop(qc, ref_path, tmp):
    """기준 얼굴에서 머리카락 위부터 목까지만 잘라 tmp에 저장하고 그 경로를 돌려준다."""
    dst = tmp / f"head2_{Path(ref_path).stem}.png"
    if dst.exists() and dst.stat().st_mtime >= Path(ref_path).stat().st_mtime:
        return dst
    img = imread_u(ref_path)
    fs = qc.faces(img, min_frac=0.0)
    if not fs:
        raise SystemExit(f"기준 얼굴에서 얼굴을 못 찾음: {Path(ref_path).name}")
    x, y, bw, bh = fs[0][:4]
    H, W = img.shape[:2]
    x0, x1 = int(max(0, x - bw * 0.55)), int(min(W, x + bw * 1.55))
    y0, y1 = int(max(0, y - bh * 0.65)), int(min(H, y + bh * 1.12))  # 턱 바로 아래까지 (옷깃 제외)
    Image.open(ref_path).convert("RGB").crop((x0, y0, x1, y1)).save(dst)
    return dst


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
            img = imread_u(refs / f"ref_{name}.png")
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
        # 이어 붙인 참조 이미지에서의 위치 (2명: 좌·우, 3명: 좌·중·우)
        pos = {1: [""], 2: [" (left)", " (right)"], 3: [" (left)", " (center)", " (right)"]}.get(len(who), [""] * len(who))
        for i, w in enumerate(who):
            prompt = prompt.replace("{" + w + "}", f"the person from the reference image{pos[i]} ({w}), same face, same hair, same age")
        text = f"{PRE} {FRAME} {prompt}"
        wf = load_wf("scene_kontext.json")
        if who:
            # 참조는 머리·목만 잘라서 넣는다: 기준 얼굴 사진의 옷(재킷 등)이 장면 의상으로 새는 것을 막는다
            ref_paths = [head_crop(qc, refs / f"ref_{w}.png", tmp) for w in who]
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
        if a.guidance:
            wf["9"]["inputs"]["guidance"] = a.guidance
        if a.lora:  # 기준 얼굴과 같은 약한 리얼리즘 LoRA
            wf["20"] = {"class_type": "LoraLoaderModelOnly",
                        "inputs": {"model": ["1", 0], "lora_name": a.lora, "strength_model": a.lora_strength}}
            wf["12"]["inputs"]["model"] = ["20", 0]
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
    global COMFY_URL
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("refs")
    r.add_argument("--prompts", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--n", type=int, default=1, help="인물당 후보 수 (2 이상이면 _candidates 폴더에 이름_1.png … 로 저장)")
    r.add_argument("--only", help="이 인물만 (쉼표 구분, 예: 서윤,윤재국)")
    r.add_argument("--guidance", type=float, default=2.3)
    r.add_argument("--lora", default="flux-super-realism.safetensors", help="models/loras 안의 파일명, 빈 문자열이면 LoRA 없이")
    r.add_argument("--lora-strength", type=float, default=0.35)
    r.add_argument("--tag", default="", help="후보 파일명 접미사 (설정 비교용)")
    s = sub.add_parser("scenes")
    s.add_argument("--prompts", required=True)
    s.add_argument("--refs", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--only")
    s.add_argument("--tries", type=int, default=4)
    s.add_argument("--guidance", type=float, default=0, help="0이면 워크플로우 기본값(참조 있음 2.5 / 없음 3.0)")
    s.add_argument("--lora", default="flux-super-realism.safetensors", help="빈 문자열이면 LoRA 없이")
    s.add_argument("--lora-strength", type=float, default=0.35)
    for p in (r, s):
        p.add_argument("--force", action="store_true")
        p.add_argument("--url", default=COMFY_URL)
    a = ap.parse_args()
    COMFY_URL = a.url
    try:
        requests.get(f"{COMFY_URL}/system_stats", timeout=5)
    except Exception:  # noqa: BLE001
        sys.exit("ComfyUI에 연결할 수 없습니다. run_comfy_8gb.bat 를 먼저 실행하세요.")
    (run_refs if a.cmd == "refs" else run_scenes)(a)


if __name__ == "__main__":
    main()
