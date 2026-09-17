import { Video } from "@remotion/media";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";

// 실제 동영상 한 컷.
//
// 화면 채움: objectFit="cover" 가 1080x1920 세로 프레임을 가득 채우도록
//   원본을 중앙 기준으로 잘라낸다. 가로 원본도 검은 여백 없이 꽉 찬다.
//   (objectFit 은 style 이 아니라 <Video> 의 전용 prop 이다.)
// offsetXPercent/offsetYPercent: 중앙 크롭을 밀어서 재프레이밍한다.
//   인물이 왼쪽에 치우친 가로 영상이면 양수로 밀어 인물을 살린다.
//   파이프라인이 EDL 의 focus 값으로부터 계산해 넘긴다.
// zoomFrom/zoomTo: 컷 안에서 천천히 밀어 넣는 punch-in.
export const VideoCut: React.FC<{
  src: string;
  trimBefore: number;
  durationInFrames: number;
  offsetXPercent: number;
  offsetYPercent: number;
  zoomFrom: number;
  zoomTo: number;
  muted: boolean;
}> = ({
  src,
  trimBefore,
  durationInFrames,
  offsetXPercent,
  offsetYPercent,
  zoomFrom,
  zoomTo,
  muted,
}) => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill name="Cut" style={{ backgroundColor: "black", overflow: "hidden" }}>
      <AbsoluteFill
        style={{
          translate: `${offsetXPercent}% ${offsetYPercent}%`,
          scale: interpolate(frame, [0, durationInFrames], [zoomFrom, zoomTo], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.33, 0, 0.67, 1),
            output: "perceptual-scale",
          }),
        }}
      >
        <Video
          src={staticFile(src)}
          trimBefore={trimBefore}
          muted={muted}
          objectFit="cover"
          style={{ width: "100%", height: "100%" }}
        />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
