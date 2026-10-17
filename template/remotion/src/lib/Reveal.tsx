import React from 'react';
import {Easing, interpolate, useCurrentFrame} from 'remotion';

type Props = {
  enter: [number, number];
  exit: [number, number];
  x?: number;
  y?: number;
  scaleFrom?: number;
  children: React.ReactNode;
};

/**
 * Enter/exit primitive for scene authors: fades and un-offsets in over `enter`,
 * ease-out, then fades and offsets back out over `exit`, ease-in. Wraps
 * children in place (not an AbsoluteFill), so it composes inside a scene's
 * own layout rather than taking over the frame. Not wired into Edit.tsx.
 */
export const Reveal: React.FC<Props> = ({enter, exit, x = 0, y = 0, scaleFrom = 1, children}) => {
  const frame = useCurrentFrame();
  const enterT = interpolate(frame, enter, [0, 1], {
    easing: Easing.out(Easing.cubic),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const exitT = interpolate(frame, exit, [1, 0], {
    easing: Easing.in(Easing.cubic),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const t = Math.min(enterT, exitT);

  return (
    <div
      style={{
        opacity: t,
        transform: `translate(${(1 - t) * x}px, ${(1 - t) * y}px) scale(${scaleFrom + (1 - scaleFrom) * t})`,
      }}
    >
      {children}
    </div>
  );
};
