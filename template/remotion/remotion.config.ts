import {Config} from '@remotion/cli/config';

// JPEG frames, not PNG: the final video is opaque and PNG encoding in Chrome
// was the render bottleneck (15 fps -> 25 fps on the same frames, measured
// 2026-09-09). Switch to 'png' only for a transparent (alpha) output.
Config.setVideoImageFormat('jpeg');
Config.setJpegQuality(90);
Config.overrideWebpackConfig((config) => config);
// Headless Chromium's default GL backend cannot create a WebGL context, which
// @remotion/three needs. Required whenever a plan uses a scene event.
Config.setChromiumOpenGlRenderer('angle');
