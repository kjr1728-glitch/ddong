"""
2단계: ComfyUI(Wan 2.2)로 샷별 클립 생성 — 완전 무료, 내 GPU 또는 Kaggle 무료 GPU

샷마다: 시작 프레임 업로드 → 워크플로우에 프롬프트/크기/시드 채우기 → 실행 →
완료 대기 → mp4 내려받기. 이미 받은 클립은 건너뛰므로 중간에 끊겨도
같은 명령으로 이어서 돌리면 됩니다.

사용법:
    python generate_clips.py --shotlist shotlist.json \
        --frames-dir output/run/frames --out-dir output/run/clips \
        --comfy-url http://127.0.0.1:8188
"""
import argparse
import json
import os
import time

from comfy_client import ComfyClient, ComfyError
from common import DEFAULT_NEGATIVE, TYPE_PREFIX, load_shotlist, video_settings, workflow_path
from workflow_patch import check_against_server, describe, load_workflow, patch_workflow


def build_prompt(shot: dict) -> str:
    prefix = TYPE_PREFIX.get(shot.get("type", "product"), "")
    return prefix + shot["prompt"].strip()


def generate(shotlist_path: str, frames_dir: str, out_dir: str, comfy_url: str,
             timeout: int = 3600, only: list = None, log=print) -> list:
    data = load_shotlist(shotlist_path)
    v = video_settings(data)
    wf_path = workflow_path(v["workflow"])
    workflow = load_workflow(wf_path)
    negative = data.get("negative_prompt") or DEFAULT_NEGATIVE

    client = ComfyClient(comfy_url)
    try:
        stats = client.ping()
    except Exception as e:
        raise SystemExit(
            f"ComfyUI({comfy_url})에 연결할 수 없습니다: {e}\n"
            "ComfyUI를 `python main.py --listen` 으로 띄웠는지, 주소가 맞는지 확인하세요."
        )
    devs = stats.get("devices") or []
    if devs:
        d = devs[0]
        log(f"ComfyUI 연결됨: {d.get('name')} (VRAM {d.get('vram_total', 0) / 2**30:.1f}GB)")

    problems = check_against_server(workflow, client)
    if problems:
        raise SystemExit("워크플로우를 실행할 수 없습니다:\n  - " + "\n  - ".join(problems))

    os.makedirs(out_dir, exist_ok=True)
    results = []
    for idx, shot in enumerate(data["shots"]):
        sid = shot["id"]
        if only and sid not in only:
            continue
        dest = os.path.join(out_dir, f"shot_{sid}.mp4")
        meta_path = os.path.join(out_dir, f"shot_{sid}.json")
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            log(f"[건너뜀] 클립이 이미 있습니다: {dest}")
            results.append(dest)
            continue

        frame = os.path.join(frames_dir, f"shot_{sid}.png")
        if not os.path.exists(frame):
            raise SystemExit(f"시작 프레임이 없습니다: {frame} (prepare_frames.py 먼저 실행)")

        seed = int(shot.get("seed", int(v["seed"]) + idx))
        positive = build_prompt(shot)
        log(f"\n[샷 {sid}] {shot['type']} / seed={seed}")
        log(f"  프롬프트: {positive[:120]}{'...' if len(positive) > 120 else ''}")

        image_name = client.upload_image(frame)
        wf = patch_workflow(
            workflow,
            image_name=image_name,
            positive=positive,
            negative=negative,
            width=int(v["width"]),
            height=int(v["height"]),
            length=int(v["length"]),
            seed=seed,
            steps=int(v["steps"]) if v.get("steps") else None,
            filename_prefix=f"shopping_shorts/shot_{sid}",
        )
        started = time.time()
        prompt_id = client.queue(wf)
        log(f"  실행 요청됨 (prompt_id={prompt_id[:8]}...) — 5초 클립 기준 GPU에 따라 2~15분")
        try:
            entry = client.wait(prompt_id, timeout=timeout, log=log)
        except ComfyError as e:
            raise SystemExit(f"샷 {sid} 생성 실패:\n{e}")

        files = client.output_files(entry)
        if not files:
            raise SystemExit(f"샷 {sid}: 결과 파일이 없습니다. 워크플로우에 SaveVideo 노드가 있는지 확인하세요.")
        chosen = files[0]
        ext = os.path.splitext(chosen["filename"])[1].lower() or ".mp4"
        if ext != ".mp4":
            dest = os.path.join(out_dir, f"shot_{sid}{ext}")
        client.download(chosen, dest)
        elapsed = time.time() - started
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({"prompt_id": prompt_id, "seed": seed, "positive": positive,
                       "workflow": os.path.basename(wf_path), "seconds": round(elapsed, 1),
                       "source": chosen}, f, ensure_ascii=False, indent=2)
        log(f"  완료: {dest} ({elapsed / 60:.1f}분)")
        results.append(dest)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shotlist", required=True)
    parser.add_argument("--frames-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--comfy-url", default=os.environ.get("COMFY_URL", "http://127.0.0.1:8188"))
    parser.add_argument("--timeout", type=int, default=3600, help="샷 하나당 최대 대기(초)")
    parser.add_argument("--only", default=None, help="쉼표로 구분한 샷 id만 다시 생성 (예: 02,04)")
    parser.add_argument("--describe", action="store_true", help="워크플로우 요약만 출력하고 종료")
    args = parser.parse_args()

    if args.describe:
        data = load_shotlist(args.shotlist)
        wf = load_workflow(workflow_path(video_settings(data)["workflow"]))
        print(json.dumps(describe(wf), ensure_ascii=False, indent=2))
        return

    only = [s.strip() for s in args.only.split(",")] if args.only else None
    clips = generate(args.shotlist, args.frames_dir, args.out_dir, args.comfy_url,
                     timeout=args.timeout, only=only)
    print(f"\n완료: 클립 {len(clips)}개 → {args.out_dir}")


if __name__ == "__main__":
    main()
