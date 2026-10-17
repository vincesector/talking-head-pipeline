export type TrackFrame = {
  frame: number;
  /** Face centre, normalized 0-1 against the source video. */
  cx: number;
  cy: number;
  /** Top of the face box, normalized. Anchor captions off this. */
  top: number;
  w: number;
  h: number;
};

export type Track = {
  fps: number;
  width: number;
  height: number;
  frames: number;
  detectionRate: number;
  track: TrackFrame[];
};

/**
 * Sample the track at a frame, interpolating between neighbours.
 *
 * The tracker runs at the source fps. If the composition runs at a different
 * fps, or a punch-in has shifted the timeline, this keeps the anchor smooth
 * instead of stepping.
 */
export const sampleTrack = (track: Track, frame: number): TrackFrame => {
  const frames = track.track;
  const clamped = Math.max(0, Math.min(frames.length - 1, frame));
  const lower = Math.floor(clamped);
  const upper = Math.min(frames.length - 1, lower + 1);
  const t = clamped - lower;

  const a = frames[lower];
  const b = frames[upper];
  const mix = (key: keyof Omit<TrackFrame, 'frame'>) => a[key] + (b[key] - a[key]) * t;

  return {
    frame: clamped,
    cx: mix('cx'),
    cy: mix('cy'),
    top: mix('top'),
    w: mix('w'),
    h: mix('h'),
  };
};
