import React from 'react';
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {resolveLayout} from './layouts';

export type ScatterItem = {
  src: string;
  /** Normalized centre. */
  x: number;
  y: number;
  /** Height as a fraction of frame height. Vary it: equal sizes read as a grid. */
  size: number;
};

type Props = {
  items: ScatterItem[];
  /** Depth blur range in PIXELS, from the plan. Nearer marks get the low end. */
  blurRange?: [number, number];
  at: number;
  hold: number;
  inFrames?: number;
  outFrames?: number;
};

/**
 * Asset marks strewn across the frame, living inside the roto sandwich so the
 * subject occludes the ones behind him.
 *
 * The occlusion is the whole effect. Items are placed deliberately across the
 * middle of frame, not pushed to the edges, because a logo that never passes
 * behind him is just an overlay and the depth never reads.
 *
 * Sizes and vertical positions are varied on purpose. Eight marks at one size
 * on one baseline is a logo wall; varied, it reads as depth.
 */
export const LogoScatter: React.FC<Props> = ({
  items,
  at,
  hold,
  blurRange,
  inFrames = 16,
  outFrames = 12,
}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const L = resolveLayout(width, height);
  const start = at - inFrames;
  const releaseStart = at + hold;
  const end = releaseStart + outFrames;

  if (frame < start || frame > end) {
    return null;
  }

  const enter = interpolate(frame, [start, at], [0, 1], {
    easing: Easing.bezier(0.22, 1, 0.36, 1),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const exit = interpolate(frame, [releaseStart, end], [1, 0], {
    easing: Easing.bezier(0.4, 0, 1, 1),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill>
      {items.map((item, i) => {
        // A badge at `size` (fraction of HEIGHT) is size*(height/width) wide.
        // On 9:16 that is 1.78x, so the same number reads three times wider
        // than on 16:9. Clamp into the profile's safe box rather than trusting
        // the authored coordinate.
        const halfW = (item.size * (height / width)) / 2;
        const halfH = item.size / 2;
        const x = Math.min(
          Math.max(item.x, L.safe.left + halfW),
          1 - L.safe.right - halfW,
        );
        const y = Math.min(
          Math.max(item.y, L.safe.top + halfH),
          1 - L.safe.bottom - halfH,
        );
        // Depth by size: within one scatter the smaller marks read as further
        // away, so they carry more defocus. Uniform blur across all of them
        // would flatten them onto a single plane, which is the thing we are
        // trying to avoid.
        const [bMin, bMax] = blurRange ?? [
          L.depth.scatterBlur[0] * height,
          L.depth.scatterBlur[1] * height,
        ];
        const span = Math.max(1e-6, L.scatter.maxSize - L.scatter.minSize);
        const nearness = Math.min(1, Math.max(0,
          (item.size - L.scatter.minSize) / span));
        const defocus = bMax - (bMax - bMin) * nearness;
        const t = Math.min(
          interpolate(enter, [i * 0.09, i * 0.09 + 0.55], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          }),
          exit,
        );
        // Nothing is ever parked. Two sines per item, decorrelated by index.
        const bob =
          Math.sin(frame * 0.045 + i * 1.7) * 5 +
          Math.sin(frame * 0.021 + i * 0.9) * 3;
        return (
          <Img
            key={item.src}
            src={staticFile(`logos/assets/${item.src}`)}
            style={{
              position: 'absolute',
              left: `${x * 100}%`,
              top: `${y * 100}%`,
              height: `${item.size * 100}vh`,
              width: 'auto',
              opacity: t,
              transform: `translate(-50%, -50%) translateY(${bob + (1 - t) * 34}px) scale(${
                0.86 + t * 0.14
              })`,
              filter: `blur(${defocus.toFixed(2)}px)`,
              willChange: 'transform, filter',
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};
