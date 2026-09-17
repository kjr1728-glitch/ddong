import { Audio } from "@remotion/media";
import { AbsoluteFill, staticFile } from "remotion";
import { CtaCard } from "./CtaCard";
import { Subtitles } from "./Subtitles";
import { CAPTIONS, CTA_TEXT, NARRATION, TOTAL_DURATION_IN_FRAMES } from "./generated/edl-data";
import { Timeline } from "./generated/Timeline";

// 쇼핑쇼츠 REMIX 최종 컴포지션.
// 바닥에 실제 동영상 컷 타임라인을 깔고, 그 위에 나레이션·자막·CTA 를 얹는다.
// 정적 그래픽(CTA)은 오버레이라서 실사 화면 비율을 깎지 않는다.
export const ShoppingShort: React.FC = () => {
  // CTA 는 마지막 1.6초 구간에 올린다.
  const ctaAppearsAt = Math.max(TOTAL_DURATION_IN_FRAMES - 48, 0);

  return (
    <AbsoluteFill name="ShoppingShort" style={{ backgroundColor: "black" }}>
      <Timeline />

      {NARRATION ? <Audio src={staticFile(NARRATION.file)} /> : null}

      <Subtitles captions={CAPTIONS} />

      {CTA_TEXT ? <CtaCard text={CTA_TEXT} appearAtFrame={ctaAppearsAt} /> : null}
    </AbsoluteFill>
  );
};
