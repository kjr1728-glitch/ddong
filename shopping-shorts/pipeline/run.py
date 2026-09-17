"""REMIX 파이프라인 오케스트레이터.

    python3 pipeline/run.py status                      현황 점검
    python3 pipeline/run.py index                       1. 소스 장면 인덱싱
    python3 pipeline/run.py analyze <url> [<url>...]    2. 레퍼런스 분석 (watch)
    python3 pipeline/run.py tts                         3. 한국어 나레이션 생성
    python3 pipeline/run.py cut                         4. 대본 ↔ 컷 매칭 (EDL)
    python3 pipeline/run.py build                       5. 코드 생성
    python3 pipeline/run.py render                      6. 최종 1080x1920 MP4
    python3 pipeline/run.py all                         3~6 연속 실행

렌더 가드:
  - narration.mp3 가 없으면 최종 렌더를 거부한다 (음성 없는 최종본 금지).
    검증용으로 화면만 보고 싶으면 `render --draft` 를 쓴다. 드래프트는
    파일명에 NO-AUDIO 가 붙고 최종본 경로에 저장되지 않는다.
  - 실사 비율이 MIN_REAL_VIDEO_RATIO 미만이면 렌더를 거부한다.
  - 길이가 목표 범위(15~30초)를 벗어나면 경고한다.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import config

HERE = Path(__file__).resolve().parent


# 이 컨테이너는 remotion.media 로의 egress 가 막혀 있어 Remotion 이 Chromium 을
# 내려받지 못한다. 이미 설치된 headless shell 이 있으면 그걸 쓴다.
# (로컬 PC 에서는 아무것도 찾지 못하고 Remotion 이 알아서 받아 쓴다.)
CHROMIUM_CANDIDATES = (
    "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell",
)


def find_chromium() -> str | None:
    if os.environ.get("REMOTION_BROWSER_EXECUTABLE"):
        return os.environ["REMOTION_BROWSER_EXECUTABLE"]
    for path in CHROMIUM_CANDIDATES:
        if Path(path).exists():
            return path
    # 패턴이 바뀐 경우를 대비해 한 번 더 찾아본다.
    for found in Path("/opt/pw-browsers").glob("*/chrome-linux/headless_shell"):
        return str(found)
    return None


def sh(cmd: list[str], *, cwd: Path | None = None) -> int:
    print(f"\n$ {' '.join(str(c) for c in cmd)}")
    env = dict(os.environ)
    chromium = find_chromium()
    if chromium:
        env["REMOTION_BROWSER_EXECUTABLE"] = chromium
    return subprocess.run(cmd, cwd=cwd or config.PROJECT_ROOT, env=env).returncode


def py(script: str, *args: str) -> int:
    return sh([sys.executable, str(HERE / script), *args])


def load_edl() -> dict | None:
    if not config.EDL_JSON.exists():
        return None
    return json.loads(config.EDL_JSON.read_text())


def cmd_status(_: argparse.Namespace) -> int:
    print("=" * 62)
    print("REMIX 파이프라인 현황")
    print("=" * 62)

    # 1. TTS 키
    if config.ELEVENLABS_API_KEY:
        print("1. ELEVENLABS_API_KEY  : 설정됨")
        rc = py("tts_elevenlabs.py", "--check")
        if rc != 0:
            print("   → 크레딧 조회 실패")
    else:
        print("1. ELEVENLABS_API_KEY  : 없음  (TTS 불가 → 최종 렌더 차단)")
        print("2. 무료 크레딧          : 확인 불가 (키 없음)")

    # 3~5. 소스와 장면 인덱스
    if config.SOURCE_INDEX.exists():
        index = json.loads(config.SOURCE_INDEX.read_text())
        owned = [s for s in index.get("sources", []) if s.get("rights") == "owned"]
        refs = index.get("references", [])
        total_s = sum(s["duration"] for s in owned)
        scenes = sum(len(s["scenes"]) for s in owned)
        print(f"3. 내 영상              : {len(owned)}개, {total_s:.1f}초")
        for s in owned:
            print(f"     {s['file']:<24} {s['duration']:>6.1f}s "
                  f"{s['width']}x{s['height']} 구간 {len(s['scenes'])}개")
        print(f"5. 장면 인덱스          : 총 {scenes}개 구간")
        if refs:
            print(f"   레퍼런스(분석 전용)  : {len(refs)}개 — 최종본 삽입 금지")
    else:
        print("3. 내 영상              : 인덱스 없음 — `run.py index` 를 먼저 실행")
        print("5. 장면 인덱스          : 없음")

    # 4. watch 다운로드 위치
    print(f"4. watch 작업 폴더      : {config.REFERENCE_DIR}")
    downloaded = list(config.REFERENCE_DIR.glob("*/"))
    print(f"   내려받은 레퍼런스     : {len(downloaded)}개")

    # 대본 / 나레이션 / EDL
    print("-" * 62)
    print(f"대본 script.json        : {'있음' if config.SCRIPT_JSON.exists() else '없음'}")
    if config.NARRATION_MP3.exists():
        from ffprobe_util import audio_duration
        print(f"나레이션 narration.mp3  : 있음 ({audio_duration(config.NARRATION_MP3):.2f}초)")
    else:
        print("나레이션 narration.mp3  : 없음")
    edl = load_edl()
    if edl:
        print(f"EDL edl.json            : 컷 {len(edl['clips'])}개, {edl['duration_s']}초, "
              f"실사 {edl['stats']['real_video_ratio']:.0%}")
    else:
        print("EDL edl.json            : 없음")
    print("=" * 62)
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    extra = ["--include-reference"] if args.include_reference else []
    return py("index_sources.py", *extra)


def cmd_analyze(args: argparse.Namespace) -> int:
    return py("analyze_reference.py", *args.urls, "--detail", args.detail)


def cmd_tts(_: argparse.Namespace) -> int:
    return py("tts_elevenlabs.py")


def cmd_cut(args: argparse.Namespace) -> int:
    extra = ["--allow-no-audio"] if args.allow_no_audio else []
    return py("select_cuts.py", *extra)


def cmd_build(_: argparse.Namespace) -> int:
    return py("gen_timeline.py")


def check_render_guards(draft: bool) -> list[str]:
    """렌더를 막아야 할 이유들을 모아서 돌려준다."""
    problems: list[str] = []

    edl = load_edl()
    if edl is None:
        return ["EDL 이 없습니다 — `run.py cut` 을 먼저 실행하세요."]

    if not draft and not config.NARRATION_MP3.exists():
        problems.append(
            "narration.mp3 가 없습니다. 음성 없는 영상을 최종본으로 렌더하지 않습니다. "
            "TTS 를 먼저 생성하거나, 화면 확인용이면 `render --draft` 를 쓰세요."
        )

    ratio = edl["stats"]["real_video_ratio"]
    if ratio < config.MIN_REAL_VIDEO_RATIO:
        problems.append(
            f"실사 영상 비율이 {ratio:.0%} 로 최소 기준 "
            f"{config.MIN_REAL_VIDEO_RATIO:.0%} 에 못 미칩니다. "
            f"sources/ 에 쓸 수 있는 영상을 더 넣으세요."
        )

    return problems


def cmd_render(args: argparse.Namespace) -> int:
    problems = check_render_guards(args.draft)
    if problems:
        print("\n[렌더 중단]", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    edl = load_edl()
    assert edl is not None
    if not (config.MIN_DURATION_S <= edl["duration_s"] <= config.MAX_DURATION_S):
        print(f"\n[경고] 길이 {edl['duration_s']:.1f}초 — 목표 범위 "
              f"{config.MIN_DURATION_S}~{config.MAX_DURATION_S}초를 벗어났습니다.")

    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = (config.OUT_DIR / "draft-NO-AUDIO.mp4") if args.draft else config.FINAL_MP4

    rc = sh(["npx", "remotion", "render", "ShoppingShort", str(dest),
             "--log", "error"])
    if rc != 0:
        return rc

    if dest.exists():
        from ffprobe_util import probe
        meta = probe(dest)
        kind = "드래프트(음성 없음)" if args.draft else "최종본"
        print(f"\n{kind}: {dest}")
        print(f"  {meta['width']}x{meta['height']}, {meta['duration']:.2f}초, "
              f"{dest.stat().st_size / 1_000_000:.1f}MB")
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    for step, fn in (("tts", cmd_tts), ("cut", cmd_cut),
                     ("build", cmd_build), ("render", cmd_render)):
        rc = fn(args)
        if rc != 0:
            print(f"\n[중단] {step} 단계에서 멈췄습니다.", file=sys.stderr)
            return rc
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="쇼핑쇼츠 REMIX 파이프라인")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="현황 점검").set_defaults(fn=cmd_status)

    p_index = sub.add_parser("index", help="소스 장면 인덱싱")
    p_index.add_argument("--include-reference", action="store_true")
    p_index.set_defaults(fn=cmd_index)

    p_an = sub.add_parser("analyze", help="레퍼런스 분석 (watch)")
    p_an.add_argument("urls", nargs="+")
    p_an.add_argument("--detail", default="balanced")
    p_an.set_defaults(fn=cmd_analyze)

    sub.add_parser("tts", help="ElevenLabs 나레이션 생성").set_defaults(fn=cmd_tts)

    p_cut = sub.add_parser("cut", help="대본 ↔ 컷 매칭")
    p_cut.add_argument("--allow-no-audio", action="store_true")
    p_cut.set_defaults(fn=cmd_cut)

    sub.add_parser("build", help="Remotion 코드 생성").set_defaults(fn=cmd_build)

    p_r = sub.add_parser("render", help="1080x1920 MP4 렌더")
    p_r.add_argument("--draft", action="store_true",
                     help="음성 없이 화면만 확인 (최종본 아님)")
    p_r.set_defaults(fn=cmd_render)

    p_all = sub.add_parser("all", help="tts → cut → build → render")
    p_all.add_argument("--draft", action="store_true")
    p_all.add_argument("--allow-no-audio", action="store_true")
    p_all.set_defaults(fn=cmd_all)

    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
