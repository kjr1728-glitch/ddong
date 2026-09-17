"""5단계 — EDL 을 Remotion 타임라인 코드로 변환한다.

Remotion 모범 사례상 편집 가능한 컷은 `.map()` 으로 만들면 안 되고 각각 독립된
JSX 노드여야 한다. 그래서 런타임에 JSON 을 순회하는 대신, 여기서 **하드코딩된
TSX 를 생성**한다. 그러면 Studio 타임라인에서 컷을 직접 드래그해 수정할 수 있다.

생성물:
  src/generated/Timeline.tsx   하드코딩된 TransitionSeries 컷 배치
  src/generated/edl-data.ts    길이·자막·CTA·오디오 메타데이터
  public/clips/*.mp4           staticFile() 로 읽을 수 있게 복사한 원본
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import config

TRANSITION_F = config.TRANSITION_F
MIN_CLIP_FOR_TRANSITION_F = config.MIN_CLIP_FOR_TRANSITION_F


def lay_out(clips: list[dict]) -> tuple[list[int], list[int], int]:
    """전환 겹침을 반영한 각 컷의 시작 프레임과 전환 길이를 계산한다.

    TransitionSeries 는 전환하는 동안 두 컷이 동시에 재생되므로 전체 길이가
    전환 길이만큼 줄어든다. 자막 타이밍도 이 값을 기준으로 잡아야 어긋나지 않는다.
    """
    transitions: list[int] = []
    for current, following in zip(clips, clips[1:]):
        ok = (current["duration_f"] >= MIN_CLIP_FOR_TRANSITION_F
              and following["duration_f"] >= MIN_CLIP_FOR_TRANSITION_F)
        transitions.append(TRANSITION_F if ok else 0)

    starts = [0]
    for i, clip in enumerate(clips[:-1]):
        starts.append(starts[i] + clip["duration_f"] - transitions[i])

    total = starts[-1] + clips[-1]["duration_f"] if clips else 0
    return starts, transitions, total


def render_timeline(clips: list[dict], transitions: list[int]) -> str:
    lines = [
        "// 이 파일은 pipeline/gen_timeline.py 가 생성합니다 — 직접 고치면 덮어써집니다.",
        "// 컷을 바꾸려면 data/edl.json 을 고친 뒤 gen_timeline.py 를 다시 실행하세요.",
        "",
        'import { TransitionSeries, linearTiming } from "@remotion/transitions";',
        'import { fade } from "@remotion/transitions/fade";',
        'import { VideoCut } from "../VideoCut";',
        "",
        "export const Timeline: React.FC = () => {",
        "  return (",
        '    <TransitionSeries name="Timeline">',
    ]

    for i, clip in enumerate(clips):
        label = f'{clip["role"] or clip["beat"]} · {clip["file"]}'
        # 원본에 말소리가 들어 있으면 나레이션과 겹치므로 음소거한다.
        muted = "true"
        lines += [
            f'      <TransitionSeries.Sequence name="{label}" '
            f'durationInFrames={{{clip["duration_f"]}}}>',
            "        <VideoCut",
            f'          src="clips/{clip["file"]}"',
            f'          trimBefore={{{clip["trim_before_f"]}}}',
            f'          durationInFrames={{{clip["duration_f"]}}}',
            f'          offsetXPercent={{{clip["offset_percent"]["x"]}}}',
            f'          offsetYPercent={{{clip["offset_percent"]["y"]}}}',
            f'          zoomFrom={{{clip["zoom"]["from"]}}}',
            f'          zoomTo={{{clip["zoom"]["to"]}}}',
            f"          muted={{{muted}}}",
            "        />",
            "      </TransitionSeries.Sequence>",
        ]
        if i < len(transitions) and transitions[i] > 0:
            lines += [
                "      <TransitionSeries.Transition",
                "        presentation={fade()}",
                f"        timing={{linearTiming({{ durationInFrames: {transitions[i]} }})}}",
                "      />",
            ]

    lines += ["    </TransitionSeries>", "  );", "};", ""]
    return "\n".join(lines)


def render_data(edl: dict, starts: list[int], total: int) -> str:
    # 자막 타이밍을 전환 겹침이 반영된 실제 시작 프레임 기준으로 다시 계산한다.
    # 한 비트가 여러 컷으로 나뉘어도 자막은 비트 전체를 덮어야 한다.
    # 같은 beat 에 속한 연속 컷을 묶어 하나의 자막 구간으로 만든다.
    captions = []
    for clip, start_f in zip(edl["clips"], starts):
        end_ms = int((start_f + clip["duration_f"]) / edl["fps"] * 1000)
        if clip.get("text"):
            captions.append({
                "text": clip["text"],
                "startMs": int(start_f / edl["fps"] * 1000),
                "endMs": end_ms,
            })
        elif captions:
            # 텍스트 없는 컷은 직전 비트의 이어지는 컷이므로 자막을 늘린다.
            captions[-1]["endMs"] = end_ms

    audio = edl.get("audio")
    audio_ts = "null"
    if audio:
        audio_ts = (f'{{ file: {json.dumps(audio["file"])}, '
                    f'durationInSeconds: {audio["duration_s"]} }}')

    return "\n".join([
        "// 이 파일은 pipeline/gen_timeline.py 가 생성합니다 — 직접 고치면 덮어써집니다.",
        "",
        'import type { Caption, NarrationInfo } from "../types";',
        "",
        f"export const FPS = {edl['fps']};",
        f"export const WIDTH = {edl['width']};",
        f"export const HEIGHT = {edl['height']};",
        f"export const TOTAL_DURATION_IN_FRAMES = {total};",
        f"export const CTA_TEXT = {json.dumps(edl.get('cta', ''), ensure_ascii=False)};",
        f"export const NARRATION: NarrationInfo | null = {audio_ts};",
        "",
        "export const CAPTIONS: Caption[] = "
        + json.dumps(captions, ensure_ascii=False, indent=2) + ";",
        "",
    ])


def copy_clips(edl: dict) -> None:
    config.PUBLIC_CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    for name in {c["file"] for c in edl["clips"]}:
        src = config.SOURCES_DIR / name
        if not src.exists():
            raise FileNotFoundError(f"소스 영상을 찾을 수 없습니다: {src}")
        shutil.copy2(src, config.PUBLIC_CLIPS_DIR / name)


def main() -> int:
    if not config.EDL_JSON.exists():
        print(f"[중단] {config.EDL_JSON} 가 없습니다. select_cuts.py 를 먼저 실행하세요.",
              file=sys.stderr)
        return 1

    edl = json.loads(config.EDL_JSON.read_text())
    clips = edl["clips"]
    if not clips:
        print("[중단] EDL 에 컷이 없습니다.", file=sys.stderr)
        return 1

    starts, transitions, total = lay_out(clips)

    out_dir = Path(config.PROJECT_ROOT / "src" / "generated")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "Timeline.tsx").write_text(render_timeline(clips, transitions))
    (out_dir / "edl-data.ts").write_text(render_data(edl, starts, total))
    copy_clips(edl)

    print(f"컷 {len(clips)}개, 전환 {sum(1 for t in transitions if t)}회")
    print(f"전환 겹침 반영 총 길이: {total}프레임 ({total / edl['fps']:.2f}초)")
    print(f"→ src/generated/Timeline.tsx")
    print(f"→ src/generated/edl-data.ts")
    print(f"→ public/clips/ 에 원본 {len({c['file'] for c in clips})}개 복사")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
