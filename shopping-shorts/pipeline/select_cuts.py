"""4단계 — 새 대본의 각 비트에 가장 적합한 실제 영상 구간을 골라 EDL 을 만든다.

입력:  data/script.json        (확정된 한국어 대본)
       data/sources.index.json (1단계 장면 인덱스)
       public/narration.mp3    (3단계 TTS, 있으면 길이를 여기에 맞춘다)
출력:  data/edl.json           (Remotion 이 읽는 편집 결정 목록)

매칭 규칙
  - 비트의 want 키워드 ↔ 장면의 label/tags 겹침을 점수로 매긴다.
  - 같은 구간을 반복해서 쓰지 않도록 이미 쓴 구간에 감점을 준다.
  - 길이가 비슷할수록 가점.
  - rights != "owned" 인 소스는 후보에서 제외한다 (저작권 규칙).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

import config

TARGET_ASPECT = config.WIDTH / config.HEIGHT


class SelectionError(RuntimeError):
    pass


def crop_loss(width: int, height: int) -> float:
    """세로 프레임에 꽉 채울 때 잘려나가는 면적 비율. 0이면 손실 없음.

    실제 잘라내기는 Remotion 쪽 objectFit "cover" 가 처리한다. 여기서는
    어느 소스가 크롭 손실이 적은지 점수에 반영하려고 계산만 한다.
    """
    if width <= 0 or height <= 0:
        return 0.0
    source_aspect = width / height
    if source_aspect > TARGET_ASPECT:
        return round(1 - TARGET_ASPECT / source_aspect, 4)   # 좌우가 잘린다
    if source_aspect < TARGET_ASPECT:
        return round(1 - source_aspect / TARGET_ASPECT, 4)   # 위아래가 잘린다
    return 0.0


def focus_offset(width: int, height: int, focus_x: float, focus_y: float) -> dict:
    """focus 지점을 살리기 위해 화면을 밀어야 하는 양 (%).

    objectFit "cover" 는 항상 중앙을 기준으로 자르므로, 중앙이 아닌 곳을 살리려면
    그만큼 반대로 밀어줘야 한다. 잘려나간 비율(crop_loss) 안에서만 움직일 수 있다.
    """
    loss = crop_loss(width, height)
    source_aspect = (width / height) if height else 1.0
    if source_aspect > TARGET_ASPECT:      # 좌우가 잘린 경우 — 가로로만 민다
        return {"x": round((0.5 - focus_x) * loss * 100, 2), "y": 0.0}
    if source_aspect < TARGET_ASPECT:      # 위아래가 잘린 경우 — 세로로만 민다
        return {"x": 0.0, "y": round((0.5 - focus_y) * loss * 100, 2)}
    return {"x": 0.0, "y": 0.0}


def score(beat: dict, scene: dict, source: dict, used: set[str], want_s: float) -> float:
    """비트에 대한 장면의 적합도. 높을수록 좋다."""
    wants = [w.strip().lower() for w in beat.get("want", []) if w.strip()]
    haystack = " ".join([scene.get("label", ""), *scene.get("tags", [])]).lower()

    s = 0.0
    if wants and haystack:
        hits = sum(1 for w in wants if w in haystack)
        s += hits * 10.0

    # 길이가 비슷할수록 좋다 (부족분에 더 큰 벌점 — 늘려 쓸 수는 없으므로).
    have = scene["duration"]
    if have >= want_s:
        s += 4.0 - min(have - want_s, 4.0) * 0.5
    else:
        s -= (want_s - have) * 2.0

    # 이미 쓴 구간은 크게 감점해서 같은 그림 반복을 피한다.
    if scene["id"] in used:
        s -= 15.0

    # 세로 프레임에 채울 때 덜 잘려나가는 소스를 선호한다.
    s -= crop_loss(source["width"], source["height"]) * 3.0

    return s


def distribute(beats: list[dict], total_s: float) -> list[float]:
    """나레이션 전체 길이를 비트 글자 수 비례로 나눈다."""
    weights = [max(len(b.get("text", "")), 1) for b in beats]
    total_w = sum(weights)
    return [total_s * w / total_w for w in weights]


def build_edl(script: dict, index: dict, narration: dict | None) -> dict:
    owned = [s for s in index.get("sources", []) if s.get("rights") == "owned"]
    if not owned:
        raise SelectionError(
            "사용 권한이 확인된 영상이 없습니다. sources/ 에 내 영상을 넣고 "
            "index_sources.py 를 다시 실행하세요. "
            "(레퍼런스 영상은 분석 전용이라 최종본에 넣을 수 없습니다.)"
        )

    beats = script.get("beats", [])
    if not beats:
        raise SelectionError("script.json 에 beats 가 없습니다.")

    if narration:
        durations = distribute(beats, narration["duration_s"])
    else:
        durations = [float(b.get("duration_s", 2.5)) for b in beats]

    candidates = [(sc, src) for src in owned for sc in src["scenes"]]
    used: set[str] = set()
    clips: list[dict] = []
    cursor_f = 0

    for beat, want_s in zip(beats, durations):
        best = max(candidates, key=lambda pair: score(beat, pair[0], pair[1], used, want_s))
        scene, source = best
        used.add(scene["id"])

        # 구간이 필요한 길이보다 길면 앞에서부터 필요한 만큼만 쓴다.
        take_s = min(want_s, scene["duration"])
        duration_f = max(int(round(take_s * config.FPS)), 1)

        clips.append({
            "beat": beat["id"],
            "role": beat.get("role", ""),
            "kind": "video",
            "source_id": source["id"],
            "scene_id": scene["id"],
            "file": source["file"],
            "src_start_s": scene["start"],
            "src_end_s": round(scene["start"] + take_s, 3),
            "from_f": cursor_f,
            "duration_f": duration_f,
            "trim_before_f": int(round(scene["start"] * config.FPS)),
            # 잘라낼 때 살릴 지점 (0~1, 0.5 가 중앙). 인물이 치우친 컷은 여기를 조정한다.
            "focus": {"x": 0.5, "y": 0.5},
            "crop_loss": crop_loss(source["width"], source["height"]),
            "offset_percent": focus_offset(
                source["width"], source["height"], 0.5, 0.5),
            # punch-in: 컷 안에서 아주 천천히 밀어 넣어 정지된 느낌을 없앤다.
            "zoom": {"from": 1.0, "to": 1.08},
            "source_has_audio": source.get("has_audio", False),
            "text": beat.get("text", ""),
        })
        cursor_f += duration_f

    total_f = cursor_f
    video_f = sum(c["duration_f"] for c in clips if c["kind"] == "video")
    ratio = video_f / total_f if total_f else 0.0

    # 자막 — 각 컷의 화면 시간에 맞춰 붙인다.
    captions = []
    for clip in clips:
        if not clip["text"]:
            continue
        captions.append({
            "text": clip["text"],
            "startMs": int(clip["from_f"] / config.FPS * 1000),
            "endMs": int((clip["from_f"] + clip["duration_f"]) / config.FPS * 1000),
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fps": config.FPS,
        "width": config.WIDTH,
        "height": config.HEIGHT,
        "duration_f": total_f,
        "duration_s": round(total_f / config.FPS, 3),
        "audio": narration,
        "clips": clips,
        "captions": captions,
        "cta": script.get("cta", ""),
        "stats": {
            "real_video_ratio": round(ratio, 4),
            "required_ratio": config.MIN_REAL_VIDEO_RATIO,
            "distinct_scenes_used": len(used),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="대본 ↔ 영상 구간 매칭 → EDL 생성")
    parser.add_argument("--allow-no-audio", action="store_true",
                        help="나레이션 없이 EDL 만 만든다 (최종 렌더는 여전히 막힌다)")
    args = parser.parse_args()

    try:
        if not config.SCRIPT_JSON.exists():
            raise SelectionError(f"{config.SCRIPT_JSON} 가 없습니다. 대본을 먼저 확정하세요.")
        if not config.SOURCE_INDEX.exists():
            raise SelectionError("sources.index.json 이 없습니다. index_sources.py 를 먼저 실행하세요.")

        script = json.loads(config.SCRIPT_JSON.read_text())
        index = json.loads(config.SOURCE_INDEX.read_text())

        narration = None
        if config.NARRATION_MP3.exists():
            from ffprobe_util import audio_duration
            narration = {
                "file": config.NARRATION_MP3.name,
                "duration_s": round(audio_duration(config.NARRATION_MP3), 3),
            }
            print(f"나레이션: {narration['file']} ({narration['duration_s']}초)")
        elif not args.allow_no_audio:
            raise SelectionError(
                "narration.mp3 가 없습니다. 먼저 TTS 를 생성하세요 "
                "(또는 --allow-no-audio 로 EDL 만 미리 만들 수 있습니다)."
            )

        edl = build_edl(script, index, narration)
        config.EDL_JSON.write_text(json.dumps(edl, ensure_ascii=False, indent=2))

        print(f"\n컷 {len(edl['clips'])}개, 총 {edl['duration_s']}초")
        for c in edl["clips"]:
            print(f"  [{c['role'] or c['beat']:<8}] {c['file']} "
                  f"{c['src_start_s']:.1f}-{c['src_end_s']:.1f}s "
                  f"→ {c['duration_f']}f  ({c['scene_id']})")
        print(f"\n실사 비율: {edl['stats']['real_video_ratio']:.0%} "
              f"(최소 {config.MIN_REAL_VIDEO_RATIO:.0%})")
        print(f"→ {config.EDL_JSON.relative_to(config.PROJECT_ROOT)} 저장")
        return 0

    except SelectionError as exc:
        print(f"[컷 선택 중단] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
