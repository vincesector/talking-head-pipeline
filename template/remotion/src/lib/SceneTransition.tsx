import React from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from 'remotion';
import type {SceneEvent} from './plan';

// HARD RULE: no zigzag "teeth" shutter, ever. It was removed from this
// component on purpose: "it looks cheesy ... don't add it anywhere else ever again".
// Scene boundaries are a fade with blur (default) or a plain fade; a liquid stinger is the
// only other acceptable transition, and it must be built as its own thing, not a shutter.

type Props = {event: SceneEvent; children: React.ReactNode};

/**
 * 0 at `from` (hidden), 1 through the steady middle, back to 0 by `to`. The first
 * `transitionFrames` ramp it up and the last `transitionFrames` ramp it down, so the in and
 * out read as mirror images of each other.
 */
const openness = (frame: number, from: number, to: number, transitionFrames: number): number => {
  const t = frame - from;
  const dur = Math.max(1, to - from);
  const inEnd = Math.min(transitionFrames, dur);
  const outStart = Math.max(0, dur - transitionFrames);
  const ease = Easing.inOut(Easing.cubic);
  if (t <= inEnd) {
    return interpolate(t, [0, inEnd], [0, 1], {easing: ease, extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  }
  if (t >= outStart) {
    return interpolate(t, [outStart, dur], [1, 0], {easing: ease, extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  }
  return 1;
};

/** Wraps a fullscreen scene for [event.from, event.to] with a fade + blur (default) or a plain fade. */
export const SceneTransition: React.FC<Props> = ({event, children}) => {
  const frame = useCurrentFrame();
  const o = openness(frame, event.from, event.to, event.transitionFrames ?? 10);
  const blur = event.transition === 'fade' ? 0 : interpolate(o, [0, 1], [18, 0]);
  const scale = interpolate(o, [0, 1], [1.04, 1]);
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{opacity: o, transform: `scale(${scale})`, filter: blur > 0.05 ? `blur(${blur}px)` : undefined}}>
        {children}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
