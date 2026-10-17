import type React from 'react';
import {DepthScene} from './DepthScene';
import {ClipScene} from './ClipScene';
import {StageScene} from './StageScene';

export type FullscreenSceneProps = {from: number; to: number; props: Record<string, unknown>};

export const FULLSCREEN_SCENES: Record<string, React.FC<FullscreenSceneProps>> = {
  depth: DepthScene,
  clip: ClipScene,
  stage: StageScene,
};
