import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame} from 'remotion';
import {camOut, rp} from './theme';

/** A transparent PNG sequence from tools/render3d: `${dir}/f####.png`, one file per PLAN frame. */
export type Seq3D = {dir: string; f0: number; f1: number};

const src = (seq: Seq3D, f: number) => staticFile(`${seq.dir}/f${String(f).padStart(4, '0')}.png`);

/**
 * 3D hero type. Lives in world space (inside the punch transform), so a push scales it with the
 * subject like a real object in the room. The renderer animates the entrance, so this only places
 * the frames. Box is centre x/y and size in composition pixels.
 */
export const Hero3D: React.FC<{seq: Seq3D; x: number; y: number; w: number; h: number}> = ({seq, x, y, w, h}) => {
  const f = useCurrentFrame();
  if (f < seq.f0 || f > seq.f1) return null;
  return (
    <AbsoluteFill>
      <Img
        src={src(seq, f)}
        style={{position: 'absolute', left: x - w / 2, top: y - h / 2, width: w, height: h, filter: 'drop-shadow(0 16px 30px rgba(0,0,0,0.5))'}}
      />
    </AbsoluteFill>
  );
};

/**
 * A rendered 3D object (logo, icon, medallion) beside the subject. Fades and rises in over 14
 * frames ending on `at` (its word), leaves from `until` (its exit word). World space.
 */
export const Asset3D: React.FC<{seq: Seq3D; at: number; until: number; x: number; y: number; size: number}> = ({seq, at, until, x, y, size}) => {
  const f = useCurrentFrame();
  if (f < seq.f0 || f > seq.f1) return null;
  const inn = rp(f, at - 14, 14);
  const out = rp(f, until, 12, camOut);
  const o = inn * (1 - out);
  if (o <= 0.001) return null;
  return (
    <AbsoluteFill>
      <Img
        src={src(seq, f)}
        style={{
          position: 'absolute',
          left: x - size / 2,
          top: y - size / 2 + (1 - inn) * 26,
          width: size,
          height: size,
          opacity: o,
          transform: `scale(${(0.82 + 0.18 * inn) * (1 - 0.06 * out)})`,
          filter: 'drop-shadow(0 18px 26px rgba(0,0,0,0.45))',
        }}
      />
    </AbsoluteFill>
  );
};
