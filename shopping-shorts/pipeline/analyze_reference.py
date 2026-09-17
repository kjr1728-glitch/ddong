"""2단계 — 레퍼런스 YouTube/TikTok 영상을 watch 스킬로 분석한다.

watch 스킬(scripts/watch.py)이 프레임 JPEG + 타임스탬프 자막을 뽑아주면,
Claude 가 그 프레임을 직접 Read 해서 아래 항목을 채운다:

    Hook / 컷 순서 / 컷 길이 / 제품 등장 시점 / 사용 장면 / 결과 장면
    카피 / TTS / CTA / 자막 / 줌·크롭 / 화면 구성

이 스크립트는 그 분석을 위한 재료를 모으고, 채워 넣을 빈 양식을 만든다.

[저작권] 레퍼런스는 rights=reference-only 로 기록된다. 사용 권한이 확인되지 않은
영상은 분석에만 쓰고 최종 상업용 영상에는 절대 삽입하지 않는다 —
select_cuts.py 가 이 표시를 보고 EDL 편입을 거부한다.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import config

WATCH_SKILL = Path.home() / ".claude" / "skills" / "watch" / "scripts" / "watch.py"

# 레퍼런스에서 뽑아내야 하는 항목. 값이 비어 있으면 아직 분석 전이라는 뜻이다.
ANALYSIS_TEMPLATE = {
    "hook": "",
    "cut_sequence": [],          # [{"index":1,"start":0.0,"end":1.4,"desc":""}]
    "cut_lengths_s": [],
    "product_first_appearance_s": None,
    "usage_scenes": [],
    "result_scenes": [],
    "copy_lines": [],
    "tts_style": "",
    "cta": "",
    "subtitle_style": "",
    "zoom_crop": "",
    "composition": "",
}


def slugify(source: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", source).strip("-")[:60] or "ref"


def is_local(source: str) -> bool:
    """URL 이 아니라 로컬 파일 경로인지."""
    return not source.lower().startswith(("http://", "https://"))


def resolve_local(source: str) -> Path:
    """상대 경로는 reference/ 기준으로도 찾아본다."""
    direct = Path(source).expanduser()
    if direct.exists():
        return direct.resolve()
    inside = (config.REFERENCE_DIR / source).expanduser()
    if inside.exists():
        return inside.resolve()
    raise FileNotFoundError(
        f"파일을 찾을 수 없습니다: {source}\n"
        f"  다음 위치를 확인했습니다: {direct}, {inside}"
    )


def run_watch(source: str, out_dir: Path, detail: str) -> tuple[bool, str]:
    """watch.py 를 돌려 프레임 + 자막을 뽑는다. (성공여부, 출력텍스트)

    source 는 URL 또는 로컬 파일 경로 둘 다 된다. 네트워크가 막힌 환경에서는
    영상을 직접 받아 reference/ 에 넣고 파일명으로 부르면 그대로 분석된다.
    """
    if not WATCH_SKILL.exists():
        return False, (
            f"watch 스킬을 찾을 수 없습니다: {WATCH_SKILL}\n"
            "세션 시작 훅(.claude/hooks/install-skills.sh)이 설치합니다."
        )

    cmd = [sys.executable, str(WATCH_SKILL), source,
           "--detail", detail, "--out-dir", str(out_dir)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    output = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode == 0, output


def main() -> int:
    parser = argparse.ArgumentParser(description="레퍼런스 영상 분석 (watch)")
    parser.add_argument("sources", nargs="+",
                        help="레퍼런스 URL, 또는 내려받아 둔 로컬 영상 파일 경로 "
                             "(상대 경로는 reference/ 기준으로도 찾습니다)")
    parser.add_argument("--detail", default="balanced",
                        choices=["transcript", "efficient", "balanced", "token-burner"],
                        help="watch 의 프레임 정밀도 (기본 balanced)")
    args = parser.parse_args()

    config.ensure_dirs()

    existing = {}
    if config.REFERENCE_ANALYSIS.exists():
        prev = json.loads(config.REFERENCE_ANALYSIS.read_text())
        existing = {r["url"]: r for r in prev.get("references", [])}

    results = []
    for source in args.sources:
        if is_local(source):
            try:
                target = str(resolve_local(source))
            except FileNotFoundError as exc:
                print(f"\n[건너뜀] {exc}")
                continue
            slug = slugify(Path(target).stem)
        else:
            target = source
            slug = slugify(source)

        out_dir = config.REFERENCE_DIR / slug
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n[watch] {target}")
        ok, output = run_watch(target, out_dir, args.detail)

        report = out_dir / "watch-report.txt"
        report.write_text(output)

        if not ok:
            print(f"  실패 — {report.relative_to(config.PROJECT_ROOT)} 참고")
        else:
            frames = sorted(out_dir.rglob("*.jpg"))
            print(f"  프레임 {len(frames)}장, 리포트 → "
                  f"{report.relative_to(config.PROJECT_ROOT)}")
            print("  다음: Claude 가 이 프레임들을 Read 해서 분석 항목을 채웁니다.")

        # 이전 분석이 있으면 유지하고, 없으면 빈 양식을 넣는다.
        entry = existing.get(source, {"url": source, "analysis": dict(ANALYSIS_TEMPLATE)})
        entry.update({
            "url": source,
            "local_file": target if is_local(source) else None,
            "slug": slug,
            "rights": "reference-only",  # 최종본 삽입 금지
            "watch_ok": ok,
            "watch_report": str(report.relative_to(config.PROJECT_ROOT)),
            "frames_dir": str(out_dir.relative_to(config.PROJECT_ROOT)),
            "analyzed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        entry.setdefault("analysis", dict(ANALYSIS_TEMPLATE))
        results.append(entry)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "references": results,
        "note": ("rights=reference-only — 분석 전용. 사용 권한이 확인되지 않은 "
                 "제3자 영상은 최종 상업용 영상에 삽입하지 않는다."),
    }
    config.REFERENCE_ANALYSIS.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\n→ {config.REFERENCE_ANALYSIS.relative_to(config.PROJECT_ROOT)} 저장")
    print("  analysis 항목이 비어 있으면 아직 분석 전입니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
