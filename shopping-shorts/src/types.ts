// EDL(편집 결정 목록)의 타입. pipeline/select_cuts.py 가 만드는 JSON 과 1:1 대응한다.

export type Crop = {
  left: number;
  right: number;
  top: number;
  bottom: number;
};

export type Caption = {
  text: string;
  startMs: number;
  endMs: number;
};

export type NarrationInfo = {
  file: string;
  durationInSeconds: number;
};
