import React from 'react';
import {interpolate} from 'remotion';
import {C, FONT, camIn, camOut, clamp} from './theme';

/**
 * The container every card sits in: rounded, soft shadow, a FULL even hairline border.
 * Never a coloured bar on one edge (top, left, anywhere): it is the first tell of a generated UI.
 * Highlight with a fill tint, a full border or text colour instead.
 */
export const Panel: React.FC<{w: number; h?: number; pad?: number; children: React.ReactNode; style?: React.CSSProperties}> = ({
  w,
  h,
  pad = 32,
  children,
  style,
}) => (
  <div
    style={{
      width: w,
      height: h,
      boxSizing: 'border-box',
      padding: pad,
      borderRadius: 22,
      background: C.panel,
      border: `1.5px solid ${C.border}`,
      boxShadow: '0 40px 90px rgba(0,0,0,0.55), 0 10px 26px rgba(0,0,0,0.35)',
      fontFamily: FONT,
      color: C.text,
      position: 'relative',
      overflow: 'hidden',
      textRendering: 'geometricPrecision',
      fontVariantNumeric: 'tabular-nums',
      ...style,
    }}
  >
    {children}
  </div>
);

/** A punch on a card: scale keys that land on a word and release on a later word. */
export type CardPunch = {at: number; until: number; ox?: number; oy?: number; s?: number};
export const cardPunch = (f: number, keys: CardPunch[] = []) => {
  for (const k of keys) {
    if (f < k.at - 9 || f > k.until + 14) continue;
    const t =
      f <= k.at
        ? interpolate(f, [k.at - 9, k.at], [0, 1], {...clamp, easing: camIn})
        : f <= k.until
          ? 1
          : interpolate(f, [k.until, k.until + 14], [1, 0], {...clamp, easing: camOut});
    return {s: 1 + ((k.s ?? 1.1) - 1) * t, ox: k.ox ?? 0.5, oy: k.oy ?? 0.5};
  }
  return {s: 1, ox: 0.5, oy: 0.5};
};
