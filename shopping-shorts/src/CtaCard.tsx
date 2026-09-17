import {
  AbsoluteFill,
  Easing,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

// CTA 는 정적 그래픽을 써도 되는 보조 장면이다 (가격·비교·강조와 함께).
// 영상 위에 겹쳐 올리므로 실사 비율을 깎아먹지 않는다.
export const CtaCard: React.FC<{ text: string; appearAtFrame: number }> = ({
  text,
  appearAtFrame,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const local = frame - appearAtFrame;

  if (local < 0) {
    return null;
  }

  return (
    <AbsoluteFill
      name="CTA"
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: 140,
      }}
    >
      <div
        style={{
          backgroundColor: "rgba(255,255,255,0.96)",
          color: "#111",
          fontSize: 54,
          fontWeight: 800,
          padding: "28px 56px",
          borderRadius: 999,
          boxShadow: "0 18px 50px rgba(0,0,0,0.45)",
          opacity: interpolate(local, [0, 0.4 * fps], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.16, 1, 0.3, 1),
          }),
          scale: interpolate(local, [0, 0.5 * fps], [0.88, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.16, 1, 0.3, 1),
            output: "perceptual-scale",
          }),
        }}
      >
        {text}
      </div>
    </AbsoluteFill>
  );
};
