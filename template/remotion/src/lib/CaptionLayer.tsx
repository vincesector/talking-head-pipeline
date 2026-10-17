import React from 'react';
import {Sequence, useCurrentFrame, useVideoConfig} from 'remotion';
import type {FontPairingId} from './fontPairings';
import {resolveLayout} from './layouts';
import {RunningCaption, type Token} from './RunningCaption';
import {sampleTrack, type Track} from './track';

export type Cue = {from: number; to: number; tokens: Token[]};

type Props = {
  cues: Cue[];
  pairing?: FontPairingId;
  /** Frame range that gets head-tracked captions. Everything else is fixed. */
  trackedUntil?: number;
  /** Normalized y for fixed captions. Defaults to the layout profile. */
  position?: number;
  /** Frame ranges where the upper frame is busy, so tracked cues drop low. */
  avoidTop?: {from: number; to: number}[];
  /** Frame ranges (e.g. fullscreen scene events) where the head is not on screen, so captions stay fixed regardless of trackedUntil. */
  fixedDuring?: {from: number; to: number}[];
  /** Frame ranges where no caption renders at all, tracked or fixed. */
  silence?: {from: number; to: number}[];
  fontSize?: number;
  accent?: string;
  track: Track;
  videoScale?: number;
  scaleOrigin?: {cx: number; cy: number};
  /** Fixed-caption centre x and box width in px for this frame (side layout / screen scene). */
  cx?: number;
  boxWidth?: number;
  /** Extra text-shadow weight 0..1, for captions over busy UI. */
  heavy?: number;
};

export const CaptionLayer: React.FC<Props> = ({
  cues,
  pairing = 'inter-instrument',
  trackedUntil = 0,
  position,
  avoidTop = [],
  fixedDuring = [],
  silence = [],
  fontSize,
  accent,
  track,
  videoScale = 1,
  scaleOrigin,
  cx,
  boxWidth,
  heavy = 0,
}) => {
  const {width, height} = useVideoConfig();
  const L = resolveLayout(width, height);
  const size = fontSize ?? Math.round(height * L.caption.size);
  const y = position ?? L.caption.y;

  // Absolute frame. Each cue renders inside a Sequence, and inside a Sequence
  // useCurrentFrame() restarts at 0, so any track lookup done in a child reads
  // the head position from the top of the video instead of now. Sample here,
  // outside the Sequences, and hand the anchor down.
  const absolute = useCurrentFrame();
  const head = sampleTrack(track, absolute);
  const projected = {
    cx: scaleOrigin
      ? scaleOrigin.cx + (head.cx - scaleOrigin.cx) * videoScale
      : head.cx,
    top: scaleOrigin
      ? scaleOrigin.cy + (head.top - scaleOrigin.cy) * videoScale
      : head.top,
    chin: scaleOrigin
      ? scaleOrigin.cy + (head.cy + head.h / 2 - scaleOrigin.cy) * videoScale
      : head.cy + head.h / 2,
  };
  const topBusy = avoidTop.some((r) => absolute >= r.from && absolute <= r.to);

  // text-shadow inherits, so one declaration on the wrapper reaches every
  // glyph. Two shadows: a tight dark one for edge definition, a wide soft one
  // to lift the text off a busy background.
  const shadow = `0 3px 10px rgba(0,0,0,0.92), 0 0 36px rgba(0,0,0,${0.7 + 0.25 * heavy})${heavy > 0.01 ? `, 0 0 18px rgba(0,0,0,${0.85 * heavy})` : ''}`;

  return (
    <>
      {cues.map((cue) => {
        // Skipped entirely, not just hidden: screenshare and other silenced
        // ranges have no head to caption over, tracked or fixed.
        // Frame-exact: nothing draws while the current frame is inside a
        // silenced range, including a cue that started just before it.
        if (silence.some((r) => absolute >= r.from && absolute <= r.to)) {
          return null;
        }
        const tracked =
          cue.from < trackedUntil &&
          !fixedDuring.some((r) => cue.from >= r.from && cue.from <= r.to);
        const body = (
          <RunningCaption
            tokens={cue.tokens}
            pairing={pairing}
            fontSize={size}
            accent={accent}
          />
        );

        return (
          <Sequence
            key={cue.from}
            from={cue.from}
            durationInFrames={Math.max(1, cue.to - cue.from)}
            layout="none"
          >
            {tracked ? (
              <div
                style={{
                  position: 'absolute',
                  left: `${projected.cx * 100}%`,
                  // Above the head normally. When the upper frame is taken by
                  // a hero word, drop below the chin instead of fighting it.
                  top: topBusy
                    ? `${(projected.chin + 0.055) * 100}%`
                    : `${(projected.top - 0.055) * 100}%`,
                  transform: topBusy
                    ? 'translate(-50%, 0)'
                    : 'translate(-50%, -100%)',
                  width: width * 0.62,
                  textShadow: shadow,
                }}
              >
                {body}
              </div>
            ) : (
              <div
                style={{
                  position: 'absolute',
                  left: cx ?? width / 2,
                  top: `${y * 100}%`,
                  width: boxWidth ?? width * L.caption.width,
                  transform: 'translate(-50%, -50%)',
                  textShadow: shadow,
                }}
              >
                {body}
              </div>
            )}
          </Sequence>
        );
      })}
    </>
  );
};
