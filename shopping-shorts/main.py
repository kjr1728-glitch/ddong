"""
쇼핑 쇼츠 무료 자동 생성 파이프라인
제품 사진 1장 → 시작 프레임 → Wan 2.2 클립(ComfyUI) → edge-tts 나레이션 → ffmpeg 합성

사용법:
    python main.py --shotlist shotlist.json
    python main.py --shotlist shotlist.json --comfy-url https://xxxx.trycloudflare.com   # Kaggle 터널
    python main.py --shotlist shotlist.json --check        # 연결/모델/ffmpeg 점검만

결과는 output/<날짜>_<제품명>/ 에 모이고, 같은 폴더로 다시 실행하면 끝난 단계는 건너뜁니다.
비용은 0원입니다. (ComfyUI는 내 GPU 또는 Kaggle 무료 GPU, TTS는 edge-tts, 합성은 ffmpeg)
"""
import argparse
import datetime
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))


def slugify(text: str) -> str:
    slug = re.sub(r"[^\w가-힣]+", "_", text).strip("_")
    return slug[:40] or "product"


def check(shotlist_path: str, comfy_url: str) -> bool:
    from comfy_client import ComfyClient
    from common import find_ffmpeg, load_shotlist, resolve, video_settings, workflow_path
    from workflow_patch import check_against_server, describe, load_workflow

    ok = True
    data = load_shotlist(shotlist_path)
    print(f"샷리스트: {len(data['shots'])}개 샷, 제품 '{data['product'].get('name')}'")

    img = resolve(data["_base_dir"], data["product"].get("image", ""))
    print(f"제품 사진: {'OK' if img and os.path.exists(img) else '없음 → ' + str(img)}")
    ok &= bool(img and os.path.exists(img))

    try:
        print(f"ffmpeg: {find_ffmpeg()}")
    except SystemExit as e:
        print(f"ffmpeg: 없음 ({e})")
        ok = False

    try:
        import edge_tts  # noqa: F401
        print("edge-tts: OK")
    except ImportError:
        print("edge-tts: 없음 (pip install -r requirements.txt)")
        ok = False

    v = video_settings(data)
    wf = load_workflow(workflow_path(v["workflow"]))
    d = describe(wf)
    print(f"워크플로우: {v['workflow']} (모델 {[m[1] for m in d['models']]})")

    client = ComfyClient(comfy_url)
    try:
        stats = client.ping()
        dev = (stats.get("devices") or [{}])[0]
        print(f"ComfyUI: 연결됨 {comfy_url} — {dev.get('name', '?')} "
              f"VRAM {dev.get('vram_total', 0) / 2**30:.1f}GB")
        problems = check_against_server(wf, client)
        for p in problems:
            print(f"  ✗ {p}")
        if not problems:
            print("  ✓ 필요한 노드와 모델 파일이 모두 있습니다")
        ok &= not problems
    except Exception as e:
        print(f"ComfyUI: 연결 실패 ({comfy_url}): {e}")
        ok = False

    print("\n점검 결과:", "모두 통과 — python main.py 로 실행하세요" if ok else "위 항목을 먼저 해결하세요")
    return ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shotlist", required=True, help="shotlist.json 경로")
    parser.add_argument("--comfy-url", default=os.environ.get("COMFY_URL", "http://127.0.0.1:8188"))
    parser.add_argument("--run-dir", default=None, help="결과 폴더 (기본: output/<날짜>_<제품명>)")
    parser.add_argument("--voice", default=None)
    parser.add_argument("--bgm", default=None, help="배경음악 파일 (선택)")
    parser.add_argument("--no-captions", action="store_true")
    parser.add_argument("--timeout", type=int, default=3600, help="샷 하나당 최대 대기(초)")
    parser.add_argument("--check", action="store_true", help="환경 점검만 하고 종료")
    parser.add_argument("--skip-clips", action="store_true",
                        help="클립 생성 건너뛰기 (clips/ 에 직접 넣은 영상으로 합성만)")
    args = parser.parse_args()

    if args.check:
        sys.exit(0 if check(args.shotlist, args.comfy_url) else 1)

    from assemble import assemble
    from common import load_shotlist
    from generate_clips import generate
    from narrate import narrate
    from prepare_frames import prepare

    data = load_shotlist(args.shotlist)
    today = datetime.date.today().isoformat()
    run_dir = args.run_dir or os.path.join(
        PROJECT_ROOT, "output", f"{today}_{slugify(data['product'].get('name', ''))}"
    )
    frames_dir = os.path.join(run_dir, "frames")
    clips_dir = os.path.join(run_dir, "clips")
    narration_dir = os.path.join(run_dir, "narration")
    final = os.path.join(run_dir, "final.mp4")
    os.makedirs(run_dir, exist_ok=True)
    print(f"작업 폴더: {run_dir}")

    print("\n[1/4] 시작 프레임")
    prepare(args.shotlist, frames_dir)

    print("\n[2/4] 클립 생성 (ComfyUI / Wan 2.2)")
    if args.skip_clips:
        print("  --skip-clips: 건너뜀")
    else:
        generate(args.shotlist, frames_dir, clips_dir, args.comfy_url, timeout=args.timeout)

    print("\n[3/4] 나레이션 (edge-tts)")
    narrate(args.shotlist, narration_dir, voice=args.voice)

    print("\n[4/4] 합성 (ffmpeg)")
    assemble(args.shotlist, clips_dir, narration_dir, final, bgm=args.bgm, no_captions=args.no_captions)

    print(f"\n영상 완성: {final}")
    print("유튜브에 올리려면: python ../youtube-automation/scripts/youtube_upload.py "
          f"--video {final} --srt {os.path.splitext(final)[0]}.srt --title \"제목\"")


if __name__ == "__main__":
    main()
