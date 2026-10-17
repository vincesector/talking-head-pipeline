import React from 'react';
import {useVideoConfig} from 'remotion';
import {
  Easing,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
} from 'remotion';
import {resolveLayout} from './layouts';

export type LogoSpec = {
  /** File under public/logos/ */
  src: string;
  label?: string;
  /** Height as a fraction of frame height. */
  size?: number;
};

type Props = {
  logos: LogoSpec[];
  from: number;
  to: number;
  /**
   * Which side of frame to occupy. On this set the left third measures 19.6
   * mean luma against 45.7 on the right, so left is the quiet side and needs
   * no plate behind it.
   */
  side?: 'left' | 'right';
  /**
   * Horizontal CENTRE, normalized. Anchoring by edge pushes marks into the
   * corner; they should sit midway between the frame edge and the subject's
   * face. Measured here: face edge 0.375, so centre 0.19.
   */
  x?: number;
  /** Vertical centre, normalized. */
  y?: number;
  inFrames?: number;
  outFrames?: number;
};

/**
 * Brand marks parked in the empty side of frame.
 *
 * No camera move needed here. He sits at x≈0.50 and his body occupies roughly
 * the middle third, so the outer third is already free. Reframing to open it
 * would cost a 33% upscale on 1080p and buy nothing.
 */
export const LogoCard: React.FC<Props> = ({
  logos,
  from,
  to,
  side = 'left',
  x,
  y,
  inFrames = 12,
  outFrames = 10,
}) => {
  const frame = useCurrentFrame();
  const {width: fw, height: fh} = useVideoConfig();
  const L = resolveLayout(fw, fh);
  const ax = x ?? L.logo.x;
  const ay = y ?? L.logo.y;
  if (frame < from || frame > to) {
    return null;
  }

  const enter = interpolate(frame, [from, from + inFrames], [0, 1], {
    easing: Easing.bezier(0.22, 1, 0.36, 1),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const exit = interpolate(frame, [to - outFrames, to], [1, 0], {
    easing: Easing.bezier(0.4, 0, 1, 1),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <div
      style={{
        position: 'absolute',
        top: `${ay * 100}%`,
        left: `${(side === 'left' || L.logo.direction === 'row' ? ax : 1 - ax) * 100}%`,
        transform: 'translate(-50%, -50%)',
        display: 'flex',
        flexDirection: L.logo.direction,
        gap: L.logo.gap,
        alignItems: 'center',
      }}
    >
      {logos.map((logo, i) => {
        // 4-frame stagger, straight from the motion blueprint.
        const t =
          Math.min(
            interpolate(enter, [i * 0.14, i * 0.14 + 0.5], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            }),
            exit,
          ) ?? 0;
        return (
          <div
            key={logo.src}
            style={{
              opacity: t,
              transform: `translateX(${(1 - t) * (side === 'left' ? -40 : 40)}px)`,
              display: 'flex',
              flexDirection: 'column',
              gap: 12,
              alignItems: 'center',
            }}
          >
            <Img
              src={staticFile(`logos/${logo.src}`)}
              style={{
                height: `${(logo.size ?? L.logo.size) * 100}vh`,
                width: 'auto',
                objectFit: 'contain',
              }}
            />
            {logo.label ? (
              <div
                style={{
                  fontFamily: '"Helvetica Neue", Helvetica, Arial, sans-serif',
                  fontWeight: 700,
                  fontSize: L.logo.direction === 'row' ? 40 : 26,  // vertical cards are read on a phone
                  letterSpacing: 2.5,
                  color: 'rgba(255,255,255,0.72)',
                  textShadow: '0 2px 10px rgba(0,0,0,0.85)',
                }}
              >
                {logo.label}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
};
