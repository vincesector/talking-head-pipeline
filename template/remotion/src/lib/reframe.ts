import {Easing, interpolate} from 'remotion';
import {sampleTrack, type Track} from './track';

/**
 * Offset punch: push in AND slide the subject to one side, opening the other
 * side as a canvas for graphics.
 *
 * The transform is `translate(dx, dy) scale(s)` about the frame centre, in
 * normalized units. A source point (fx, fy) lands at:
 *
 *   sx = 0.5 + (fx - 0.5) * s + dx
 *
 * so to put the face on a target x:
 *
 *   dx = tx - 0.5 - (fx - 0.5) * s
 *
 * Using translate+scale rather than a shifted transform-origin matters: the
 * origin form divides by (1 - s) and blows up as the move starts, which is
 * exactly when you need it to behave.
 */

/**
 * The video must still cover the frame, so the translation is bounded:
 *
 *   |dx| <= (s - 1) / 2
 *
 * Push past that and you reveal the edge of the footage. This is the whole
 * constraint of the technique: how far you can slide is set by how far you
 * zoomed.
 */
export const maxShift = (scale: number): number => Math.max(0, (scale - 1) / 2);

/**
 * Smallest scale that can park a face at `targetX` without revealing an edge.
 *
 * Falls out of combining the two equations above:
 *   moving right: s >= tx / fx
 *   moving left:  s >= (1 - tx) / (1 - fx)
 *
 * Consequence worth knowing before you record: this is asymmetric around where
 * you sit. Sit left of centre and sliding further left is cheap while sliding
 * right is expensive, because the right side of the frame has to stretch all
 * the way across.
 */
export const minScaleFor = (faceX: number, targetX: number): number =>
  targetX > faceX ? targetX / faceX : (1 - targetX) / (1 - faceX);

export type ReframeShot = {
  /** Frame the move completes on. */
  at: number;
  /** Frames held in the reframed position. */
  hold: number;
  /** Which side the SUBJECT moves to. Graphics go on the other side. */
  subjectSide: 'left' | 'right';
  /** Where the face lands, normalized. Defaults to the rule-of-thirds line. */
  targetX?: number;
  /** Overrides the computed minimum. */
  scale?: number;
  inFrames?: number;
  outFrames?: number;
};

export type ReframeState = {
  scale: number;
  dx: number;
  dy: number;
  /** 0 at base framing, 1 fully reframed. Drive graphics off this. */
  progress: number;
  /** True if the requested move was clamped to keep the frame covered. */
  clamped: boolean;
};

const IDENTITY: ReframeState = {scale: 1, dx: 0, dy: 0, progress: 0, clamped: false};

/**
 * A reframe travels much further than a punch-in, so it runs longer. 14 frames
 * (467ms) in, 18 (600ms) out. Same asymmetry as the punch: the arrival is the
 * event, the return is housekeeping.
 */
const DEFAULT_IN = 14;
const DEFAULT_OUT = 18;

const EASE_IN = Easing.bezier(0.32, 0, 0.16, 1);
const EASE_OUT = Easing.bezier(0.4, 0, 0.25, 1);

/** Keeps the footage edge off the frame edge, so subpixel rounding can't bite. */
const EDGE_MARGIN = 0.004;

export const reframeAt = (
  frame: number,
  shots: ReframeShot[],
  track: Track,
): ReframeState => {
  for (const shot of shots) {
    const inFrames = shot.inFrames ?? DEFAULT_IN;
    const outFrames = shot.outFrames ?? DEFAULT_OUT;
    const start = shot.at - inFrames;
    const releaseStart = shot.at + shot.hold;
    const end = releaseStart + outFrames;

    if (frame < start || frame > end) {
      continue;
    }

    // Lock the framing to where the face is when the move lands. Recomputing
    // every frame makes the frame chase the subject, which reads like a bad
    // gimbal rather than an operator setting a shot.
    const anchor = sampleTrack(track, shot.at);
    const targetX =
      shot.targetX ?? (shot.subjectSide === 'left' ? 1 / 3 : 2 / 3);

    const needed = minScaleFor(anchor.cx, targetX);
    const scale = shot.scale ?? needed + 0.05;

    let dx = targetX - 0.5 - (anchor.cx - 0.5) * scale;
    // Vertical stays where it is. The push already tightens the headroom.
    let dy = anchor.cy - 0.5 - (anchor.cy - 0.5) * scale;

    const limit = Math.max(0, maxShift(scale) - EDGE_MARGIN);
    const clamped = Math.abs(dx) > limit || Math.abs(dy) > limit;
    dx = Math.max(-limit, Math.min(limit, dx));
    dy = Math.max(-limit, Math.min(limit, dy));

    let progress: number;
    if (frame <= shot.at) {
      progress = interpolate(frame, [start, shot.at], [0, 1], {
        easing: EASE_IN,
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
      });
    } else if (frame <= releaseStart) {
      progress = 1;
    } else {
      progress = interpolate(frame, [releaseStart, end], [1, 0], {
        easing: EASE_OUT,
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
      });
    }

    return {
      scale: 1 + (scale - 1) * progress,
      dx: dx * progress,
      dy: dy * progress,
      progress,
      clamped,
    };
  }

  return IDENTITY;
};

/** CSS transform for a reframe state. Apply with transformOrigin 50% 50%. */
export const reframeTransform = (
  state: ReframeState,
  width: number,
  height: number,
): string =>
  `translate(${(state.dx * width).toFixed(3)}px, ${(state.dy * height).toFixed(3)}px) scale(${state.scale.toFixed(5)})`;

/**
 * Where a source point ends up on screen. Needed to keep tracked captions and
 * graphics glued to the subject through the move.
 */
export const projectPoint = (
  state: ReframeState,
  x: number,
  y: number,
): {x: number; y: number} => ({
  x: 0.5 + (x - 0.5) * state.scale + state.dx,
  y: 0.5 + (y - 0.5) * state.scale + state.dy,
});
