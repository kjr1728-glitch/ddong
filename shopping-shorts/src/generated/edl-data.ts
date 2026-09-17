// 이 파일은 pipeline/gen_timeline.py 가 생성합니다 — 직접 고치면 덮어써집니다.

import type { Caption, NarrationInfo } from "../types";

export const FPS = 30;
export const WIDTH = 1080;
export const HEIGHT = 1920;
export const TOTAL_DURATION_IN_FRAMES = 654;
export const CTA_TEXT = "지금 무료로 사주 보기";
export const NARRATION: NarrationInfo | null = { file: "narration.mp3", durationInSeconds: 21.629 };

export const CAPTIONS: Caption[] = [
  {
    "text": "요즘 이상하게 일이 안 풀린다면",
    "startMs": 0,
    "endMs": 3600
  },
  {
    "text": "그건 운이 아니라 흐름의 문제일 수 있어요",
    "startMs": 3400,
    "endMs": 8200
  },
  {
    "text": "연화가 사주로 그 흐름을 읽어드립니다",
    "startMs": 8000,
    "endMs": 12266
  },
  {
    "text": "생년월일만 넣으면 삼 분 만에",
    "startMs": 12066,
    "endMs": 15433
  },
  {
    "text": "올해 내 재물운과 시기를 알려드려요",
    "startMs": 15233,
    "endMs": 19100
  },
  {
    "text": "지금 무료로 확인해보세요",
    "startMs": 18900,
    "endMs": 21800
  }
];
