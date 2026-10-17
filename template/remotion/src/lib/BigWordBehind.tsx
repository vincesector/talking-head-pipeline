import {fitText} from '@remotion/layout-utils';
import React from 'react';
import {
  AbsoluteFill,
  Easing,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {displayFaces, type DisplayFaceId} from './displayFaces';
import {resolveLayout} from './layouts';

type Props = {
  /** Space-separated words. Pass `lines` to control the stack explicitly. */
  text: string;
  /** Explicit line breaks, e.g. ['NOT', 'AMERICAN']. */
  lines?: string[];
  /** Frame the word is fully in. Should be the frame he says it. */
  at: number;
  hold: number;
  /**
   * Total stack height as a fraction of frame height. Condensed faces reach
   * 0.8 comfortably where a normal-width face would have shrunk to fit width.
   */
  size?: number;
  face?: DisplayFaceId;
  /** Depth blur in PIXELS. Comes from the plan, which knows the lens. */
  blur?: number;
  /**
   * Vertical nudge as a fraction of frame height, negative is up. Use it to
   * keep a stacked word clear of the caption band; a white caption landing on
   * white letters is unreadable no matter how good the drop shadow is.
   */
  y?: number;
  color?: string;
  inFrames?: number;
  outFrames?: number;
  /**
   * The scale currently applied by the shared punch/reframe transform this
   * component is nested inside (see Edit.tsx: video, matte and this all share
   * one ancestor transform so nothing drifts apart during a punch). fitText
   * sizes this text against the raw frame dimensions with no knowledge of
   * that ancestor scale, so when a punch is active on the same beat (by
   * design, e.g. a hard punch landing on the same word), the parent
   * transform multiplies the text by `scale` again on top, and it overflows
   * the frame by exactly that factor. Dividing the final size by `scale`
   * cancels it out so "sits inside the frame" holds regardless of what punch
   * is riding underneath. Defaults to 1 (no ancestor scale).
   */
  scale?: number;
};

const LINE_HEIGHT = 0.82;

/**
 * Hero word set between the base video and the matte, so the subject occludes
 * it.
 *
 * Stacking is the point when the phrase is two words. Width is the binding
 * constraint, not height, so two short lines each go far bigger than one long
 * line ever could. "NOT AMERICAN" on one line is small and timid; stacked it
 * fills the frame.
 *
 * The reveal IS the occlusion, so the word enters from behind the subject
 * rather than fading on top of them, and settles down from slightly larger.
 * No glow or box-shadow: they ghost against a matte edge and give the cutout
 * away.
 */
export const BigWordBehind: React.FC<Props> = ({
  text,
  lines,
  at,
  hold,
  size,
  face = 'anton',
  blur,
  y,
  color = '#ffffff',
  inFrames = 9,
  outFrames = 12,
  scale = 1,
}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const L = resolveLayout(width, height);
  const stackSize = size ?? L.bigWord.size;
  const bias = y ?? L.bigWord.y;
  // Sits between him and the background, so it cannot be perfectly sharp.
  // Plan value is in pixels and authoritative; the profile fallback is a
  // fraction of frame height and only a guess when the lens is unknown.
  const defocus = blur ?? L.depth.heroBlur * height;
  const start = at - inFrames;
  const releaseStart = at + hold;
  const end = releaseStart + outFrames;

  if (frame < start || frame > end) {
    return null;
  }

  const enter = interpolate(frame, [start, at], [0, 1], {
    easing: Easing.bezier(0, 0, 0.2, 1),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const exit = interpolate(frame, [releaseStart, end], [1, 0], {
    easing: Easing.bezier(0.4, 0, 1, 1),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const t = Math.min(enter, exit);

  const rows = (lines ?? text.split(/\s+/)).map((l) => l.toUpperCase());
  const spec = displayFaces[face];

  // Width is bound by the longest line, height by the whole stack. Take
  // whichever limit binds first, or a long word renders as a fragment and
  // reads as a bug rather than a design.
  const longest = rows.reduce((a, b) => (a.length >= b.length ? a : b));
  const byWidth = fitText({
    text: longest,
    withinWidth: width * L.bigWord.widthLimit,
    fontFamily: spec.fontFamily,
    fontWeight: spec.fontWeight,
    letterSpacing: spec.letterSpacing,
    validateFontIsLoaded: true,
  }).fontSize;
  const byHeight = (height * stackSize) / (rows.length * LINE_HEIGHT);
  // Divide by the ancestor's current punch/reframe scale: this component
  // renders inside that same transformed layer, which multiplies the final
  // on-screen size by `scale` again. Without this, a punch landing on the
  // same beat as the word (the usual case, since a hero number and its punch
  // are deliberately timed together) blows the fit past the frame edge.
  const fontSize = Math.min(byWidth, byHeight) / scale;

  return (
    <AbsoluteFill
      style={{
        justifyContent: 'center',
        alignItems: 'center',
        opacity: t,
        transform: `translateY(${bias * 100}%)`,
      }}
    >
      <div
        style={{
          fontFamily: spec.fontFamily,
          fontWeight: spec.fontWeight,
          letterSpacing: spec.letterSpacing,
          fontSize,
          lineHeight: LINE_HEIGHT,
          color,
          textAlign: 'center',
          whiteSpace: 'nowrap',
          transform: `scale(${1 + (1 - t) * 0.06})`,
          filter: `blur(${defocus.toFixed(2)}px)`,
          willChange: 'transform, filter',
        }}
      >
        {rows.map((row, i) => (
          <div key={`${row}-${i}`}>{row}</div>
        ))}
      </div>
    </AbsoluteFill>
  );
};
