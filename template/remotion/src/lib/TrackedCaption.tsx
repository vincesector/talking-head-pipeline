import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {sampleTrack, type Track} from './track';

type Props = {
  track: Track;
  children: React.ReactNode;
  /**
   * How far above the top of the head to sit, as a fraction of frame height.
   * 0.06 at 1920px is about 115px of clearance.
   */
  offset?: number;
  /** Scale applied to the underlying video, so the caption follows a punch-in. */
  videoScale?: number;
  /** transform-origin of the video scale, normalized 0-1. */
  scaleOrigin?: {cx: number; cy: number};
};

/**
 * Caption anchored to the top of the tracked head.
 *
 * The tracking JSON is in source-video normalized space. When the video below
 * is scaled by a punch-in, the head moves on screen, so the same transform has
 * to be applied to the anchor or the caption slides off the head mid-punch.
 */
export const TrackedCaption: React.FC<Props> = ({
  track,
  children,
  offset = 0.06,
  videoScale = 1,
  scaleOrigin,
}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const head = sampleTrack(track, frame);

  const origin = scaleOrigin ?? {cx: 0.5, cy: 0.5};
  // Replicate the video's scale transform about its origin.
  const x = (origin.cx + (head.cx - origin.cx) * videoScale) * width;
  const y = (origin.cy + (head.top - offset - origin.cy) * videoScale) * height;

  return (
    <div
      style={{
        position: 'absolute',
        left: x,
        top: y,
        transform: 'translate(-50%, -100%)',
        willChange: 'transform',
      }}
    >
      {children}
    </div>
  );
};
