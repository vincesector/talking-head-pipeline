import {Easing, interpolate} from 'remotion';

/**
 * Punch-in curve system.
 *
 * Both curves ease at BOTH ends. The previous attack was Material's decelerate
 * curve, cubic-bezier(0, 0, 0.2, 1), which begins at maximum velocity: 41% of
 * the travel was spent in the first 15% of the duration. That is what makes a
 * push read as fast and mechanical rather than operated. Nothing physical
 * starts at full speed.
 *
 * Quadratic ease-in-out was measured against circular and cubic before being
 * chosen. Its velocity profile is a triangle, constant acceleration then
 * constant deceleration, which is literally what a hand on a zoom ring does.
 * Circular looks smoothest as a formula and is the worst of the three in
 * practice: its derivative spikes at the midpoint, so on a 15 frame move one
 * single frame carries 36% of the travel and it reads as a snap. Quadratic's
 * busiest frame carries 13%.
 *
 * The release uses sine, which is gentler still, because a pull-out that gets
 * noticed is a pull-out that failed.
 *
 * Durations roughly doubled for the same reason: 7 frames is 0.23s, which is
 * too little time for any curve to be legible as a curve.
 */
const ATTACK = Easing.inOut(Easing.quad);
const RELEASE = Easing.inOut(Easing.sin);

export type PunchPreset = 'micro' | 'standard' | 'hard' | 'cut' | 'sustain' | 'accent';

type PunchSpec = {
  scale: number;
  inFrames: number;
  outFrames: number;
};

/** Frame counts assume 30fps. At 60fps, double them. */
// Halved after review: the earlier timings read as slow ("faster in and faster out").
export const PRESETS: Record<PunchPreset, PunchSpec> = {
  // Barely conscious. Use to keep a long take alive, not to emphasise.
  micro: {scale: 1.07, inFrames: 8, outFrames: 12},
  // The workhorse. Lands on an emphasis word.
  standard: {scale: 1.16, inFrames: 8, outFrames: 12},
  // A number, a name, a punchline. Travels furthest in the least time.
  hard: {scale: 1.28, inFrames: 6, outFrames: 10},
  // No animation. Scale changes on a jump cut, the common short-form style.
  cut: {scale: 1.18, inFrames: 0, outFrames: 0},

  // A long, gentle push held across a whole passage. Use this instead of
  // firing three separate punches at three emphasis words in one sentence.
  // Slow in and out so the arrival is barely noticed; the value is the hold.
  sustain: {scale: 1.10, inFrames: 14, outFrames: 18},

  // A small extra bump layered INSIDE a sustain, on the one word in the
  // passage that deserves more than the rest. Composes with whatever is
  // already active rather than replacing it.
  accent: {scale: 1.08, inFrames: 6, outFrames: 9},
};

export type Punch = {
  /** Frame the punch lands on. The move finishes here, it does not start here. */
  at: number;
  /** Frames to stay held at full scale after landing. */
  hold: number;
  preset?: PunchPreset;
  /** Override the preset scale without changing its timing. */
  scale?: number;
};

/**
 * Scale at a given frame for a list of punches.
 *
 * `at` is the landing frame, so the animation runs from `at - inFrames`. This
 * is the part editors get wrong: if you start the move on the emphasis word,
 * the move arrives late and the emphasis is already gone.
 *
 * Overlapping punches **compose**: their deltas multiply. That is what makes
 * the sustain-plus-accent shape work. A 1.08 sustain held across a sentence
 * with a 1.06 accent on its key word reads as one continuous move that leans
 * in briefly, which is what an operator does. Replacing instead of composing
 * would make the accent cancel the sustain and snap back, and it is why three
 * separate punches in one sentence feel like a twitch rather than a push.
 */
export const punchScale = (frame: number, punches: Punch[]): number => {
  let scale = 1;

  for (const punch of punches) {
    const spec = PRESETS[punch.preset ?? 'standard'];
    const peak = punch.scale ?? spec.scale;
    const start = punch.at - spec.inFrames;
    const releaseStart = punch.at + punch.hold;
    const end = releaseStart + spec.outFrames;

    if (frame < start || frame > end) {
      continue;
    }

    let contribution: number;
    if (frame <= punch.at) {
      contribution = interpolate(frame, [start, punch.at], [1, peak], {
        easing: ATTACK,
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
      });
    } else if (frame <= releaseStart) {
      contribution = peak;
    } else {
      contribution = interpolate(frame, [releaseStart, end], [peak, 1], {
        easing: RELEASE,
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
      });
    }
    scale *= contribution;
  }

  return scale;
};

/**
 * Where to scale from, in CSS transform-origin percentages.
 *
 * Scaling from the frame centre drifts the head out of frame whenever the
 * speaker is off-centre. Feeding the tracked face position in keeps the face
 * anchored through the whole move.
 */
export const punchOrigin = (face?: {cx: number; cy: number}): string => {
  if (!face) {
    return '50% 50%';
  }
  return `${(face.cx * 100).toFixed(2)}% ${(face.cy * 100).toFixed(2)}%`;
};
