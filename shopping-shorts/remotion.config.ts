/**
 * Note: When using the Node.JS APIs, the config file
 * doesn't apply. Instead, pass options directly to the APIs.
 *
 * All configuration options: https://remotion.dev/docs/config
 */

import { Config } from "@remotion/cli/config";
import { enableTailwind } from '@remotion/tailwind-v4';

Config.setRspack(true);
Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.overrideBundlerConfig(enableTailwind);

// 이 환경은 remotion.media 로의 egress 가 막혀 있어 Chromium 을 내려받을 수 없다.
// 컨테이너에 이미 설치된 Chromium 을 쓰도록 경로를 지정한다.
// 로컬 PC에서는 이 값이 없으면 Remotion 이 알아서 받아 쓴다.
if (process.env.REMOTION_BROWSER_EXECUTABLE) {
  Config.setBrowserExecutable(process.env.REMOTION_BROWSER_EXECUTABLE);
}
