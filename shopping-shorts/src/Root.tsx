import { Composition } from "remotion";
import { ShoppingShort } from "./ShoppingShort";
import {
  FPS,
  HEIGHT,
  TOTAL_DURATION_IN_FRAMES,
  WIDTH,
} from "./generated/edl-data";
import "./index.css";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="ShoppingShort"
      component={ShoppingShort}
      durationInFrames={TOTAL_DURATION_IN_FRAMES}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
    />
  );
};
