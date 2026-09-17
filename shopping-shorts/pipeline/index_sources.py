"""1단계 — 재사용 가능한 동영상 소스를 장면 단위로 인덱싱한다.

출력 예시 (data/sources.index.json):

    source01.mp4
      00:01.2-00:03.8  제품 클로즈업
      00:05.1-00:08.4  음료 붓기

장면 전환이 감지되지 않는 통짜 클립은 FALLBACK_SEGMENT_S 간격으로 강제 분할해서
컷으로 쓸 수 있는 구간을 만든다. 각 구간의 중간 프레임을 썸네일로 뽑아두므로,
watch 스킬이나 사람이 나중에 label 을 채워 넣을 수 있다.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import config
from ffprobe_util import MediaError, detect_scene_cuts, extract_thumb, probe

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


def fmt_ts(seconds: float) -> str:
    """00:01.2 형태로 표기."""
    minutes, secs = divmod(seconds, 60)
    return f"{int(minutes):02d}:{secs:04.1f}"


def segment(duration: float, cuts: list[float]) -> list[tuple[float, float]]:
    """장면 전환 시각 목록을 (시작, 끝) 구간 목록으로 바꾼다."""
    if cuts:
        boundaries = [0.0, *cuts, duration]
    else:
        # 컷 전환이 없는 통짜 클립 — 고정 간격으로 쪼갠다.
        boundaries = []
        t = 0.0
        while t < duration:
            boundaries.append(round(t, 3))
            t += config.FALLBACK_SEGMENT_S
        boundaries.append(round(duration, 3))

    spans = []
    for start, end in zip(boundaries, boundaries[1:]):
        if end - start >= config.MIN_SCENE_S:
            spans.append((round(start, 3), round(end, 3)))
    # 전부 너무 짧아서 걸러졌다면 통째로 한 구간으로 둔다.
    return spans or [(0.0, round(duration, 3))]


def index_dir(directory: Path, rights: str, prefix: str) -> list[dict]:
    files = sorted(p for p in directory.glob("*") if p.suffix.lower() in VIDEO_EXTS)
    sources: list[dict] = []

    for n, path in enumerate(files, start=1):
        source_id = f"{prefix}{n:02d}"
        try:
            meta = probe(path)
        except MediaError as exc:
            print(f"  [건너뜀] {path.name}: {exc}")
            continue

        cuts = detect_scene_cuts(path, config.SCENE_THRESHOLD)
        spans = segment(meta["duration"], cuts)

        scenes = []
        for i, (start, end) in enumerate(spans, start=1):
            scene_id = f"{source_id}_s{i:02d}"
            thumb = config.THUMBS_DIR / f"{scene_id}.jpg"
            got_thumb = extract_thumb(path, (start + end) / 2, thumb)
            scenes.append({
                "id": scene_id,
                "start": start,
                "end": end,
                "duration": round(end - start, 3),
                "label": "",        # 사람 또는 watch 가 채운다 ("제품 클로즈업" 등)
                "tags": [],          # 컷 선택기가 매칭에 사용한다
                "thumb": str(thumb.relative_to(config.PROJECT_ROOT)) if got_thumb else None,
            })

        sources.append({
            "id": source_id,
            "file": path.name,
            "path": str(path.relative_to(config.PROJECT_ROOT)),
            "rights": rights,
            "scene_cuts_detected": len(cuts),
            "segmented_by": "scene-change" if cuts else "fixed-interval",
            **meta,
            "scenes": scenes,
        })

        print(f"  {path.name}  ({meta['duration']:.1f}s, {meta['width']}x{meta['height']}, "
              f"컷 {len(cuts)}개 → 구간 {len(scenes)}개, 권한={rights})")
        for sc in scenes:
            label = sc["label"] or "(라벨 없음)"
            print(f"      {fmt_ts(sc['start'])}-{fmt_ts(sc['end'])}  {label}")

    return sources


def main() -> int:
    parser = argparse.ArgumentParser(description="동영상 소스를 장면 단위로 인덱싱")
    parser.add_argument("--include-reference", action="store_true",
                        help="reference/ 의 제3자 영상도 분석 전용으로 인덱싱한다")
    args = parser.parse_args()

    config.ensure_dirs()

    print(f"[내 영상] {config.SOURCES_DIR}")
    sources = index_dir(config.SOURCES_DIR, rights="owned", prefix="source")
    if not sources:
        print("  (없음) — 상업용 최종본에 쓰려면 sources/ 에 영상을 넣으세요")

    references: list[dict] = []
    if args.include_reference:
        print(f"\n[레퍼런스 — 분석 전용] {config.REFERENCE_DIR}")
        references = index_dir(config.REFERENCE_DIR, rights="reference-only", prefix="ref")
        if not references:
            print("  (없음)")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": sources,
        "references": references,
        "note": "rights=reference-only 인 항목은 분석 전용이며 최종 EDL 에 넣을 수 없다.",
    }
    config.SOURCE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    config.SOURCE_INDEX.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    usable = sum(s["duration"] for s in sources)
    print(f"\n→ {config.SOURCE_INDEX.relative_to(config.PROJECT_ROOT)} 저장")
    print(f"  사용 가능한 내 영상 총 길이: {usable:.1f}초 "
          f"(목표 쇼츠 {config.MIN_DURATION_S}~{config.MAX_DURATION_S}초)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
