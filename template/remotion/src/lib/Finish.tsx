import React from 'react';
import {AbsoluteFill} from 'remotion';

const GRAIN_SVG =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E";

type Props = {grain?: number; vignette?: number};

/**
 * Final-pass grade. Static per frame, so no useCurrentFrame here: nothing in
 * either layer animates, it is a constant look laid over the whole comp.
 */
export const Finish: React.FC<Props> = ({grain, vignette}) => (
  <>
    {grain && grain > 0 ? (
      <AbsoluteFill
        style={{
          backgroundImage: `url("${GRAIN_SVG}")`,
          mixBlendMode: 'multiply',
          opacity: grain,
          pointerEvents: 'none',
        }}
      />
    ) : null}
    {vignette && vignette > 0 ? (
      <AbsoluteFill
        style={{
          background: 'radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,1) 100%)',
          opacity: vignette,
          pointerEvents: 'none',
        }}
      />
    ) : null}
  </>
);
