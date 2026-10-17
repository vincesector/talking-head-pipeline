// A pre-rendered full-screen animation (canvas/p5/WebGL rendered to mp4 outside Remotion,
// e.g. a p5.js or three.js piece) played over the talking head. Muted: the voice carries.
// The clip starts on the scene's `from` frame; `props.startFrom` skips into it.
import React from 'react';
import {AbsoluteFill, OffthreadVideo, Sequence, staticFile} from 'remotion';
import type {FullscreenSceneProps} from './registry';

export const ClipScene: React.FC<FullscreenSceneProps> = ({from, to, props}) => (
  <Sequence from={from} durationInFrames={to - from + 1} layout="none">
    <AbsoluteFill style={{backgroundColor: (props.bg as string) ?? '#000'}}>
      <OffthreadVideo
        src={staticFile(props.src as string)}
        startFrom={(props.startFrom as number) ?? 0}
        muted
        style={{width: '100%', height: '100%', objectFit: 'cover'}}
      />
    </AbsoluteFill>
  </Sequence>
);
