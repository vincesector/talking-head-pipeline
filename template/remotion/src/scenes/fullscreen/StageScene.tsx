import React from 'react';
import {Img, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {Stage, World, camAt, chromeOpacity, punchKeys} from '../../lib/Stage';
import {resolveLayout} from '../../lib/layouts';
import {C} from '../../lib/theme';
import type {FullscreenSceneProps} from './registry';

/**
 * A code-built full-screen scene: an image (chart, screenshot, diagram exported at 2x) on a Stage,
 * with real zooms that land on words and the edge fade that keeps the caption band clear.
 *
 * props: {src, title?, punches: [{at, out, s, x, y}]}   (frames absolute, x/y in design px)
 * Build richer scenes the same way: Stage + World + punchKeys, React for the content.
 */
type Punch = {at: number; out: number; s: number; x: number; y: number};

export const StageScene: React.FC<FullscreenSceneProps> = ({props}) => {
  const f = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const D = width >= height ? {w: 1920, h: 1080} : {w: 1080, h: 1920};
  const rest = {x: D.w / 2, y: D.h / 2};
  const keys = ((props.punches as Punch[]) ?? []).flatMap((p) => punchKeys(p.at, p.out, p.s, p.x, p.y, rest));
  const cam = camAt(f, keys, rest);
  // the band where captions live, in design px: content fades out above it, never slices text
  const bandTop = (resolveLayout(width, height).caption.y - 0.06) * D.h;
  return (
    <Stage design={D}>
      <World cam={cam} w={D.w} h={D.h} bandTop={bandTop}>
        <Img
          src={staticFile(props.src as string)}
          style={{position: 'absolute', left: D.w * 0.08, top: D.h * 0.1, width: D.w * 0.84, height: bandTop - D.h * 0.16, objectFit: 'contain'}}
        />
      </World>
      {props.title ? (
        <div style={{position: 'absolute', left: 72, top: 64, fontSize: 30, fontWeight: 600, color: C.muted, opacity: chromeOpacity(cam)}}>
          {props.title as string}
        </div>
      ) : null}
    </Stage>
  );
};
