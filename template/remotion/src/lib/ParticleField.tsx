import React, {useMemo} from 'react';
import {useCurrentFrame} from 'remotion';

/**
 * Ambient drifting-particle layer, ported from Editframe's examples
 * (extras/ParticleField.tsx, MIT) with Remotion's clock. Deterministic for a
 * seed. Drop it under a sparse scene: dust, bokeh, embers, whatever the colour
 * says. `blend: 'screen'` makes light particles glow on a dark backdrop.
 */
export type ParticleFieldProps = {
  count?: number;
  color?: string;
  opacity?: number;
  /** Drift speed multiplier. 1 = slow. */
  speed?: number;
  /** Min and max radius in px. */
  sizeRange?: [number, number];
  seed?: number;
  blend?: 'normal' | 'screen';
  /** Soft edge on each dot, 0 to 1. */
  softness?: number;
};

const mulberry32 = (seed: number) => () => {
  let t = (seed += 0x6d2b79f5);
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

export const ParticleField: React.FC<ParticleFieldProps> = ({
  count = 40,
  color = '#ffffff',
  opacity = 0.18,
  speed = 1,
  sizeRange = [2, 5],
  seed = 1337,
  blend = 'screen',
  softness = 0.6,
}) => {
  const frame = useCurrentFrame();
  const particles = useMemo(() => {
    const rand = mulberry32(seed);
    return Array.from({length: count}, (_, i) => ({
      id: i,
      x: rand() * 100,
      y: rand() * 100,
      r: sizeRange[0] + rand() * (sizeRange[1] - sizeRange[0]),
      driftX: (rand() - 0.5) * 40,
      driftY: (rand() - 0.5) * 30,
      phase: rand() * Math.PI * 2,
      alpha: opacity * (0.5 + rand() * 0.8),
    }));
  }, [count, seed, sizeRange[0], sizeRange[1], opacity]);
  const t = frame / 60 / speed;
  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden', pointerEvents: 'none', mixBlendMode: blend}}>
      {particles.map((p) => (
        <div
          key={p.id}
          style={{
            position: 'absolute',
            left: `${p.x}%`,
            top: `${p.y}%`,
            width: p.r * 2,
            height: p.r * 2,
            borderRadius: '50%',
            background: `radial-gradient(circle, ${color} ${Math.round((1 - softness) * 100)}%, transparent 100%)`,
            opacity: p.alpha,
            transform: `translate(${Math.sin(t + p.phase) * p.driftX}px, ${Math.cos(t * 0.8 + p.phase) * p.driftY}px)`,
          }}
        />
      ))}
    </div>
  );
};
