import {interpolate} from 'remotion';

export const clamp = {
  extrapolateLeft: 'clamp',
  extrapolateRight: 'clamp',
} as const;

export const easeOutCubic = (value: number) => 1 - Math.pow(1 - value, 3);

export const normalizedProgress = (
  frame: number,
  start: number,
  duration: number,
) => interpolate(frame, [start, start + duration], [0, 1], clamp);

export const revealProgress = (
  frame: number,
  start: number,
  duration: number,
) => easeOutCubic(normalizedProgress(frame, start, duration));

export const arcY = (progress: number) => {
  if (progress < 0.58) {
    return interpolate(progress, [0, 0.58], [30, -9], clamp);
  }

  return interpolate(progress, [0.58, 1], [-9, 0], clamp);
};
