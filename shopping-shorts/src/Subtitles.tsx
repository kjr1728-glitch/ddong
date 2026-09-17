import {
  AbsoluteFill,
  Easing,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { Caption } from "./types";

// 쇼츠 자막. 화면 하단 안전영역 위에 놓고, 각 줄이 뜨고 질 때만 살짝 움직인다.
// 1080px 폭 기준 44px 이상 — 폰에서 읽히는 최소 크기다.
export const Subtitles: React.FC<{ captions: Caption[] }> = ({ captions }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const nowMs = (frame / fps) * 1000;

  const active = captions.find((c) => nowMs >= c.startMs && nowMs < c.endMs);
  if (!active) {
    return null;
  }

  const startFrame = (active.startMs / 1000) * fps;
  const local = frame - startFrame;

  return (
    <AbsoluteFill
      name="Subtitles"
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingLeft: 80,
        paddingRight: 80,
        paddingBottom: 300,
      }}
    >
      <div
        style={{
          fontSize: 62,
          fontWeight: 800,
          lineHeight: 1.3,
          textAlign: "center",
          color: "white",
          // 어떤 배경 위에서도 읽히도록 외곽선 + 그림자를 함께 준다.
          WebkitTextStroke: "8px rgba(0,0,0,0.85)",
          paintOrder: "stroke fill",
          textShadow: "0 8px 28px rgba(0,0,0,0.6)",
          opacity: interpolate(local, [0, 4], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.16, 1, 0.3, 1),
          }),
          translate: interpolate(local, [0, 6], ["0px 18px", "0px 0px"], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.16, 1, 0.3, 1),
          }),
        }}
      >
        {active.text}
      </div>
    </AbsoluteFill>
  );
};
