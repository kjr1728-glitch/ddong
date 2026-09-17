"""
전체 파이프라인 실행
1) 트렌드 리서치 → 2) 스크립트 작성(검토 지점) → 3) 나레이션 → 4) b-roll → 5) 합성

사용법:
    python main.py --keyword "미스터리"
    python main.py --keyword "미스터리" --auto-script     # 사람 개입 없이 끝까지

실행할 때마다 output/<날짜>_<키워드>/ 폴더를 따로 만들어 그 안에 결과를 넣습니다.
매일 자동 실행해도 어제 만든 스크립트를 그대로 다시 쓰거나 결과를 덮어쓰는 일이
없습니다. 같은 폴더로 다시 실행하면 이미 끝난 단계는 건너뛰고 이어서 진행합니다.

2단계(스크립트 작성)는 기본적으로 사람이 검토하도록 일시정지합니다.
--auto-script를 주면 ANTHROPIC_API_KEY로 스크립트까지 자동 생성합니다 (종량 과금).
"""
import argparse
import datetime
import os
import re
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")


def run(cmd: list):
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(f"실패: {' '.join(cmd)}")


def script_path(name: str) -> str:
    return os.path.join(SCRIPTS_DIR, name)


def slugify(text: str) -> str:
    slug = re.sub(r"[^\w가-힣]+", "_", text).strip("_")
    return slug[:40] or "topic"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--region", default="KR")
    parser.add_argument("--voice", default="ko-KR-SunHiNeural")
    parser.add_argument("--minutes", type=int, default=5, help="목표 영상 길이(분)")
    parser.add_argument(
        "--broll-count", type=int, default=6,
        help="키워드당 b-roll 개수. 많을수록 같은 장면 반복이 줄어듭니다",
    )
    parser.add_argument(
        "--broll-keywords",
        default=None,
        help="쉼표로 구분된 영어 b-roll 검색어. 생략 시 스크립트의 [SECTION: ... | keywords] 태그에서 자동 추출",
    )
    parser.add_argument(
        "--auto-script",
        action="store_true",
        help="스크립트까지 Anthropic API로 자동 생성 (종량 과금, 무인 실행용)",
    )
    parser.add_argument(
        "--run-dir",
        default=None,
        help="결과를 넣을 폴더 (기본값: output/<날짜>_<키워드>)",
    )
    parser.add_argument(
        "--refresh-trends",
        action="store_true",
        help="트렌드 데이터가 이미 있어도 다시 조회",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="완성된 영상을 유튜브에 올립니다 (OAuth 인증 필요)",
    )
    parser.add_argument(
        "--privacy",
        default="private",
        choices=["private", "unlisted", "public"],
        help="업로드 공개 설정. 기본값 private — 확인 전에 전체 공개되는 것을 막습니다.",
    )
    parser.add_argument("--title", default=None, help="업로드 제목 (생략 시 스크립트에서 생성)")
    parser.add_argument("--tags", default=None, help="쉼표로 구분된 업로드 태그")
    parser.add_argument(
        "--cut-seconds", type=float, default=None,
        help="한 컷의 길이(초). 짧을수록 빠른 느낌 (기본 4초)",
    )
    parser.add_argument("--no-zoom", action="store_true", help="느린 확대 끄기 (렌더링이 빨라짐)")
    parser.add_argument("--no-music", action="store_true", help="배경음악 넣지 않기")
    args = parser.parse_args()

    today = datetime.date.today().isoformat()
    run_dir = args.run_dir or os.path.join(
        PROJECT_ROOT, "output", f"{today}_{slugify(args.keyword)}"
    )
    broll_dir = os.path.join(run_dir, "broll")
    os.makedirs(run_dir, exist_ok=True)

    trends_file = os.path.join(run_dir, "trends.json")
    script_file = os.path.join(run_dir, "script.txt")
    narration_file = os.path.join(run_dir, "narration.mp3")
    srt_file = os.path.join(run_dir, "narration.srt")
    video_file = os.path.join(run_dir, "final_video.mp4")

    print(f"작업 폴더: {run_dir}")

    # 1단계: 트렌드 리서치 (이미 있으면 건너뜀)
    if os.path.exists(trends_file) and not args.refresh_trends:
        print(f"\n[건너뜀] 트렌드 데이터가 이미 있습니다: {trends_file}")
        print("         다시 조회하려면 --refresh-trends를 붙이세요.")
    else:
        run(
            [
                sys.executable,
                script_path("trend_research.py"),
                "--keyword", args.keyword,
                "--region", args.region,
                "--output", trends_file,
            ]
        )

    # 2단계: 스크립트 작성 (검토 지점)
    if os.path.exists(script_file):
        print(f"\n[건너뜀] 스크립트가 이미 있습니다: {script_file}")
    elif args.auto_script:
        run(
            [
                sys.executable,
                script_path("script_writer.py"),
                "--trends", trends_file,
                "--minutes", str(args.minutes),
                "--output", script_file,
            ]
        )
    else:
        print(
            f"\n[일시정지] 트렌드 데이터가 준비되었습니다:\n"
            f"  {trends_file}\n\n"
            "Claude Code에게 이 파일 내용을 보여주고 스크립트를 요청한 뒤,\n"
            f"결과를 아래 경로에 저장하세요:\n"
            f"  {script_file}\n\n"
            "문단마다 [SECTION: 한글 소주제 | english search keywords] 태그를 넣어달라고\n"
            "요청하면, 배경 영상 검색어가 자동으로 추출되어 사람 입력 없이 진행됩니다.\n\n"
            "저장한 뒤 같은 명령을 다시 실행하면 이어서 진행합니다.\n"
            "(API로 자동 생성하려면 --auto-script)"
        )
        return

    # 3단계: 나레이션 + 자막
    # 크기가 0인 파일은 이전 실행이 중간에 끊긴 흔적이므로 다시 만듭니다.
    if os.path.exists(narration_file) and os.path.getsize(narration_file) > 0:
        print(f"\n[건너뜀] 나레이션이 이미 있습니다: {narration_file}")
    else:
        run(
            [
                sys.executable,
                script_path("narration.py"),
                "--script", script_file,
                "--voice", args.voice,
                "--output", narration_file,
                "--srt", srt_file,
            ]
        )

    # 4단계: b-roll 수집 — 스크립트의 섹션 태그에서 검색어를 자동으로 뽑는다
    broll_cmd = [
        sys.executable,
        script_path("broll_fetcher.py"),
        "--count", str(args.broll_count),
        "--output-dir", broll_dir,
    ]
    if args.broll_keywords:
        broll_cmd += ["--keywords", args.broll_keywords]
    else:
        broll_cmd += ["--from-script", script_file]
    run(broll_cmd)

    # 5단계: 영상 합성
    synth_cmd = [
        sys.executable,
        script_path("video_synthesis.py"),
        "--narration", narration_file,
        "--broll-dir", broll_dir,
        "--script", script_file,
        "--srt", srt_file,
        "--output", video_file,
    ]
    if args.cut_seconds:
        synth_cmd += ["--cut-seconds", str(args.cut_seconds)]
    if args.no_zoom:
        synth_cmd.append("--no-zoom")
    if args.no_music:
        synth_cmd.append("--no-music")
    run(synth_cmd)

    print(f"\n영상 완성: {video_file}")

    # 6단계: 유튜브 업로드 (명시적으로 요청했을 때만)
    if args.upload:
        upload_cmd = [
            sys.executable,
            script_path("youtube_upload.py"),
            "--video", video_file,
            "--script", script_file,
            "--srt", srt_file,
            "--privacy", args.privacy,
        ]
        if args.title:
            upload_cmd += ["--title", args.title]
        if args.tags:
            upload_cmd += ["--tags", args.tags]
        run(upload_cmd)
    else:
        print(f"자막 파일(업로드 시 함께 올라갑니다): {srt_file}")
        print("유튜브에 자동으로 올리려면 --upload를 붙이세요.")

    print("\n파이프라인 완료")


if __name__ == "__main__":
    main()
