import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {C, FONT, camIn, camOut, clamp} from './theme';

/**
 * Full-frame host for a code-built scene (charts, UI, diagrams). Children are authored in a fixed
 * design space (`design`, default 1920x1080 or 1080x1920 by aspect) and scaled to the composition,
 * so one scene renders crisply at any output size. Opaque: the talking head underneath is covered.
 */
export const Stage: React.FC<{children?: React.ReactNode; background?: boolean; design?: {w: number; h: number}}> = ({
  children,
  background = true,
  design,
}) => {
  const {width, height} = useVideoConfig();
  const D = design ?? (width >= height ? {w: 1920, h: 1080} : {w: 1080, h: 1920});
  const k = Math.min(width / D.w, height / D.h);
  return (
    <AbsoluteFill style={{backgroundColor: C.bg, overflow: 'hidden'}}>
      <div
        style={{
          position: 'absolute',
          left: (width - D.w * k) / 2,
          top: (height - D.h * k) / 2,
          width: D.w,
          height: D.h,
          transform: `scale(${k})`,
          transformOrigin: '0 0',
          fontFamily: FONT,
          color: C.text,
          overflow: 'hidden',
          // geometricPrecision: without it, static text jitters by a subpixel between frames
          // while anything on the stage animates.
          textRendering: 'geometricPrecision',
        }}
      >
        {background ? <Background /> : null}
        {children}
      </div>
    </AbsoluteFill>
  );
};

/** Dark backdrop that never sits dead still: two slow corner glows and fine moving grain (no banding). */
export const Background: React.FC<{glow?: string}> = ({glow = 'rgba(255,179,92,0.10)'}) => {
  const t = useCurrentFrame();
  const drift = Math.sin(t / 90) * 18;
  return (
    <AbsoluteFill style={{backgroundColor: C.bg}}>
      <AbsoluteFill style={{background: `radial-gradient(55% 60% at ${88 + drift * 0.15}% ${2 + drift * 0.1}%, ${glow} 0%, rgba(11,12,14,0) 75%)`}} />
      <AbsoluteFill style={{background: `radial-gradient(50% 45% at ${6 - drift * 0.12}% 104%, ${glow} 0%, rgba(11,12,14,0) 70%)`}} />
      <AbsoluteFill
        style={{
          opacity: 0.06,
          mixBlendMode: 'overlay',
          backgroundImage:
            "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/></filter><rect width='240' height='240' filter='url(%23n)'/></svg>\")",
          backgroundPosition: `${(t * 37) % 240}px ${(t * 53) % 240}px`,
        }}
      />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------------------------
// Camera over a stage. World = the design space. A key puts world point (x, y) at frame centre
// at scale s. REST is identity, so a layout centred on the design centre keeps pixel-equal
// margins at rest. Pushes ease quad in/out, releases sine in/out.

export type CamKey = {at: number; s: number; x: number; y: number};

export const camAt = (frame: number, keys: CamKey[], rest: {x: number; y: number}) => {
  const ks = [...keys].sort((a, b) => a.at - b.at);
  if (!ks.length) return {s: 1, ...rest};
  if (frame <= ks[0].at) return ks[0];
  for (let i = 1; i < ks.length; i++) {
    const a = ks[i - 1];
    const b = ks[i];
    if (frame <= b.at) {
      const t = interpolate(frame, [a.at, b.at], [0, 1], {...clamp, easing: b.s >= a.s ? camIn : camOut});
      return {s: a.s + (b.s - a.s) * t, x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t};
    }
  }
  return ks[ks.length - 1];
};

/**
 * Keys for one punch on a stage: rest until `at - attack`, arrive at scale s centred on (x, y) ON
 * `at` (the word), hold, release over `release` frames from `out` (the exit word). Concatenate.
 * Centre on the element so its left and right margins are pixel-equal; a real zoom (1.6-2.2x),
 * never a small sideways nudge.
 */
export const punchKeys = (at: number, out: number, s: number, x: number, y: number, rest: {x: number; y: number}, attack = 16, release = 20): CamKey[] => [
  {at: at - attack, s: 1, ...rest},
  {at, s, x, y},
  {at: Math.max(at + 1, out), s, x, y},
  {at: Math.max(at + 1, out) + release, s: 1, ...rest},
];

export const camTransform = (c: {s: number; x: number; y: number}, w: number, h: number) =>
  `translate(${w / 2}px, ${h / 2}px) scale(${c.s}) translate(${-c.x}px, ${-c.y}px)`;

/** Opacity for fixed chrome (a wordmark, a source line): gone as soon as the camera leaves rest. */
export const chromeOpacity = (c: {s: number}) => 1 - Math.min(1, Math.max(0, (c.s - 1) / 0.06));

/**
 * Applies a camera to its children, with the EDGE FADE: zoomed content fades out over 30 px above
 * `bandTop`, so the caption band below it is never covered and no text is ever sliced by the frame
 * edge under the captions. Captions stay outside the World and never zoom.
 */
export const World: React.FC<{cam: {s: number; x: number; y: number}; w: number; h: number; bandTop: number; children: React.ReactNode}> = ({
  cam,
  w,
  h,
  bandTop,
  children,
}) => (
  <AbsoluteFill
    style={{
      maskImage: `linear-gradient(to bottom, black 0px, black ${bandTop - 30}px, transparent ${bandTop}px)`,
      WebkitMaskImage: `linear-gradient(to bottom, black 0px, black ${bandTop - 30}px, transparent ${bandTop}px)`,
    }}
  >
    <AbsoluteFill style={{transform: camTransform(cam, w, h), transformOrigin: '0 0'}}>{children}</AbsoluteFill>
  </AbsoluteFill>
);
