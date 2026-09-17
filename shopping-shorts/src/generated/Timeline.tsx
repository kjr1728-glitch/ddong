// 이 파일은 pipeline/gen_timeline.py 가 생성합니다 — 직접 고치면 덮어써집니다.
// 컷을 바꾸려면 data/edl.json 을 고친 뒤 gen_timeline.py 를 다시 실행하세요.

import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { VideoCut } from "../VideoCut";

export const Timeline: React.FC = () => {
  return (
    <TransitionSeries name="Timeline">
      <TransitionSeries.Sequence name="hook · greeting.mp4" durationInFrames={75}>
        <VideoCut
          src="clips/greeting.mp4"
          trimBefore={0}
          durationInFrames={75}
          offsetXPercent={0.0}
          offsetYPercent={0.0}
          zoomFrom={1.0}
          zoomTo={1.08}
          muted={true}
        />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 6 })}
      />
      <TransitionSeries.Sequence name="hook · invite.mp4" durationInFrames={39}>
        <VideoCut
          src="clips/invite.mp4"
          trimBefore={225}
          durationInFrames={39}
          offsetXPercent={0.0}
          offsetYPercent={0.0}
          zoomFrom={1.0}
          zoomTo={1.08}
          muted={true}
        />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 6 })}
      />
      <TransitionSeries.Sequence name="problem · greeting.mp4" durationInFrames={75}>
        <VideoCut
          src="clips/greeting.mp4"
          trimBefore={75}
          durationInFrames={75}
          offsetXPercent={0.0}
          offsetYPercent={0.0}
          zoomFrom={1.0}
          zoomTo={1.08}
          muted={true}
        />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 6 })}
      />
      <TransitionSeries.Sequence name="problem · invite.mp4" durationInFrames={75}>
        <VideoCut
          src="clips/invite.mp4"
          trimBefore={0}
          durationInFrames={75}
          offsetXPercent={0.0}
          offsetYPercent={0.0}
          zoomFrom={1.0}
          zoomTo={1.08}
          muted={true}
        />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 6 })}
      />
      <TransitionSeries.Sequence name="product · invite.mp4" durationInFrames={75}>
        <VideoCut
          src="clips/invite.mp4"
          trimBefore={75}
          durationInFrames={75}
          offsetXPercent={0.0}
          offsetYPercent={0.0}
          zoomFrom={1.0}
          zoomTo={1.08}
          muted={true}
        />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 6 })}
      />
      <TransitionSeries.Sequence name="product · invite.mp4" durationInFrames={59}>
        <VideoCut
          src="clips/invite.mp4"
          trimBefore={150}
          durationInFrames={59}
          offsetXPercent={0.0}
          offsetYPercent={0.0}
          zoomFrom={1.0}
          zoomTo={1.08}
          muted={true}
        />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 6 })}
      />
      <TransitionSeries.Sequence name="usage · greeting.mp4" durationInFrames={75}>
        <VideoCut
          src="clips/greeting.mp4"
          trimBefore={150}
          durationInFrames={75}
          offsetXPercent={0.0}
          offsetYPercent={0.0}
          zoomFrom={1.0}
          zoomTo={1.08}
          muted={true}
        />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 6 })}
      />
      <TransitionSeries.Sequence name="usage · invite.mp4" durationInFrames={32}>
        <VideoCut
          src="clips/invite.mp4"
          trimBefore={0}
          durationInFrames={32}
          offsetXPercent={0.0}
          offsetYPercent={0.0}
          zoomFrom={1.0}
          zoomTo={1.08}
          muted={true}
        />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 6 })}
      />
      <TransitionSeries.Sequence name="result · invite.mp4" durationInFrames={75}>
        <VideoCut
          src="clips/invite.mp4"
          trimBefore={150}
          durationInFrames={75}
          offsetXPercent={0.0}
          offsetYPercent={0.0}
          zoomFrom={1.0}
          zoomTo={1.08}
          muted={true}
        />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 6 })}
      />
      <TransitionSeries.Sequence name="result · invite.mp4" durationInFrames={47}>
        <VideoCut
          src="clips/invite.mp4"
          trimBefore={225}
          durationInFrames={47}
          offsetXPercent={0.0}
          offsetYPercent={0.0}
          zoomFrom={1.0}
          zoomTo={1.08}
          muted={true}
        />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 6 })}
      />
      <TransitionSeries.Sequence name="cta · invite.mp4" durationInFrames={75}>
        <VideoCut
          src="clips/invite.mp4"
          trimBefore={75}
          durationInFrames={75}
          offsetXPercent={0.0}
          offsetYPercent={0.0}
          zoomFrom={1.0}
          zoomTo={1.08}
          muted={true}
        />
      </TransitionSeries.Sequence>
      <TransitionSeries.Sequence name="cta · invite.mp4" durationInFrames={12}>
        <VideoCut
          src="clips/invite.mp4"
          trimBefore={225}
          durationInFrames={12}
          offsetXPercent={0.0}
          offsetYPercent={0.0}
          zoomFrom={1.0}
          zoomTo={1.08}
          muted={true}
        />
      </TransitionSeries.Sequence>
    </TransitionSeries>
  );
};
