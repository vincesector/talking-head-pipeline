import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
import {fontPairings, FontPairingId} from './fontPairings';
import {
  arcY,
  clamp,
  normalizedProgress,
  revealProgress,
} from './motionCurves';

const INK = '#15130f';
const YELLOW = '#f4c636';
const BLUE = '#4c69d8';

type EffectTextProps = {
  lead?: string;
  emphasis?: string;
  pairing?: FontPairingId;
  scale?: number;
};

const stageStyle: React.CSSProperties = {
  width: '100%',
  height: '100%',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  color: INK,
};

export const BaseCaption: React.FC<EffectTextProps> = ({
  lead = 'caption text',
  emphasis = '',
  pairing = 'inter-apple-garamond',
  scale = 1,
}) => {
  const frame = useCurrentFrame();
  const fonts = fontPairings[pairing];
  const progress = revealProgress(frame, 0, 8);

  return (
    <div style={stageStyle}>
      <div
        style={{
          maxWidth: 660,
          color: INK,
          fontFamily: fonts.baseFamily,
          fontSize: 82,
          fontWeight: fonts.baseWeight,
          lineHeight: 0.94,
          textAlign: 'center',
          letterSpacing: 0,
          opacity: progress,
          transform: `translateY(${(1 - progress) * 20}px) scale(${scale})`,
          transformOrigin: '50% 50%',
        }}
      >
        {lead}{' '}
        {emphasis ? (
          <span
            style={{
              color: BLUE,
              fontFamily: fonts.emphasisFamily,
              fontWeight: fonts.emphasisWeight,
              fontStyle: fonts.emphasisStyle,
            }}
          >
            {emphasis}
          </span>
        ) : null}
      </div>
    </div>
  );
};

export const WiggleCaption: React.FC<EffectTextProps> = ({
  lead = 'texto do capcut',
  emphasis = '+ animação',
  pairing = 'helvetica-instrument',
  scale = 1,
}) => {
  const frame = useCurrentFrame();
  const fonts = fontPairings[pairing];

  const renderWord = (
    text: string,
    lineIndex: number,
    family: string,
    color: string,
  ) => (
    <div
      style={{
        display: 'flex',
        justifyContent: 'center',
        fontFamily: family,
        color,
        whiteSpace: 'pre',
      }}
    >
      {Array.from(text).map((character, index) => {
        const phase = frame * 0.47 + index * 0.92 + lineIndex * 1.8;
        const y = Math.sin(phase) * 2.2;
        const skew = Math.sin(phase * 0.73) * 1.25;
        const stretch = 1 + Math.sin(phase * 0.61) * 0.025;
        const rotation = Math.sin(phase * 0.42) * 0.65;

        return (
          <span
            key={`${lineIndex}-${index}`}
            style={{
              display: 'inline-block',
              transformOrigin: '50% 60%',
              transform: `translateY(${y}px) skewY(${skew}deg) scaleY(${stretch}) rotate(${rotation}deg)`,
            }}
          >
            {character === ' ' ? '\u00a0' : character}
          </span>
        );
      })}
    </div>
  );

  return (
    <div style={stageStyle}>
      <div
        style={{
          transform: `scale(${scale})`,
          textAlign: 'center',
          lineHeight: 0.86,
          letterSpacing: 0,
        }}
      >
        <div style={{fontSize: 83, fontWeight: 900}}>
          {renderWord(lead, 0, fonts.baseFamily, YELLOW)}
        </div>
        <div
          style={{
            marginTop: 22,
            fontSize: 116,
            fontWeight: fonts.emphasisWeight,
            fontStyle: fonts.emphasisStyle,
          }}
        >
          {renderWord(emphasis, 1, fonts.emphasisFamily, BLUE)}
        </div>
      </div>
    </div>
  );
};

export const RevealCaption: React.FC<EffectTextProps> = ({
  lead = 'texto do capcut',
  emphasis = '+ animação',
  pairing = 'helvetica-instrument',
  scale = 1,
}) => {
  const frame = useCurrentFrame();
  const fonts = fontPairings[pairing];
  const tokens = lead.split(' ');
  const serifProgress = revealProgress(frame, 39, 28);
  const serifBlur = interpolate(serifProgress, [0, 0.68, 1], [18, 5, 0], clamp);

  return (
    <div style={stageStyle}>
      <div
        style={{
          transform: `scale(${scale})`,
          textAlign: 'center',
          letterSpacing: 0,
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            gap: 24,
            color: YELLOW,
            fontFamily: fonts.baseFamily,
            fontSize: 83,
            fontWeight: 900,
            lineHeight: 1,
          }}
        >
          {tokens.map((token, index) => {
            const progress = revealProgress(frame, 18 + index * 5, 10);
            const blur = interpolate(progress, [0, 0.72, 1], [12, 3, 0], clamp);
            return (
              <span
                key={token}
                style={{
                  display: 'inline-block',
                  opacity: progress,
                  filter: `blur(${blur}px)`,
                  transform: `translateY(${(1 - progress) * 64}px) scaleY(${interpolate(
                    progress,
                    [0, 0.45, 1],
                    [0.73, 1.28, 1],
                    clamp,
                  )})`,
                }}
              >
                {token}
              </span>
            );
          })}
        </div>
        <div
          style={{
            marginTop: 22,
            color: BLUE,
            fontFamily: fonts.emphasisFamily,
            fontSize: 116,
            fontWeight: fonts.emphasisWeight,
            fontStyle: fonts.emphasisStyle,
            lineHeight: 0.9,
            opacity: serifProgress,
            filter: `blur(${serifBlur}px)`,
            transform: `translateY(${(1 - serifProgress) * 106}px) scale(${
              0.88 + serifProgress * 0.12
            })`,
          }}
        >
          {emphasis}
        </div>
      </div>
    </div>
  );
};

const ArchedLine: React.FC<{
  text: string;
  start: number;
  fontFamily: string;
  fontSize: number;
  fontWeight: number;
  fontStyle: 'normal' | 'italic';
  color: string;
  finalArch: number;
  stagger: number;
  duration: number;
}> = ({
  text,
  start,
  fontFamily,
  fontSize,
  fontWeight,
  fontStyle,
  color,
  finalArch,
  stagger,
  duration,
}) => {
  const frame = useCurrentFrame();

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'center',
        color,
        fontFamily,
        fontSize,
        fontWeight,
        fontStyle,
        lineHeight: 0.9,
        whiteSpace: 'pre',
      }}
    >
      {Array.from(text).map((character, index) => {
        const denominator = Math.max(1, text.length - 1);
        const normalizedIndex = (index / denominator) * 2 - 1;
        const settledY = Math.pow(Math.abs(normalizedIndex), 1.55) * finalArch;
        const settledRotation = normalizedIndex * 3.2;
        const progress = normalizedProgress(
          frame,
          start + index * stagger,
          duration,
        );
        const eased = 1 - Math.pow(1 - progress, 3);
        const y = arcY(eased) + settledY * eased;
        const rotation = interpolate(
          eased,
          [0, 0.58, 1],
          [-11, 4, settledRotation],
          clamp,
        );
        const glyphScale = interpolate(
          eased,
          [0, 0.58, 1],
          [0.72, 1.06, 1],
          clamp,
        );

        return (
          <span
            key={index}
            style={{
              display: 'inline-block',
              opacity: interpolate(progress, [0, 0.18, 1], [0, 1, 1], clamp),
              transformOrigin: '50% 100%',
              transform: `translateY(${y}px) rotate(${rotation}deg) scale(${glyphScale})`,
            }}
          >
            {character === ' ' ? '\u00a0' : character}
          </span>
        );
      })}
    </div>
  );
};

export const ArchedRevealCaption: React.FC<EffectTextProps> = ({
  lead = 'texto+',
  emphasis = 'animação',
  pairing = 'helvetica-instrument',
  scale = 1,
}) => {
  const fonts = fontPairings[pairing];

  return (
    <div style={stageStyle}>
      <div
        style={{
          transform: `scale(${scale})`,
          textAlign: 'center',
          letterSpacing: 0,
        }}
      >
        <ArchedLine
          text={lead}
          start={0}
          fontFamily={fonts.baseFamily}
          fontSize={96}
          fontWeight={900}
          fontStyle="normal"
          color={YELLOW}
          finalArch={8}
          stagger={1.6}
          duration={11}
        />
        <div style={{height: 2}} />
        <ArchedLine
          text={emphasis}
          start={14}
          fontFamily={fonts.emphasisFamily}
          fontSize={158}
          fontWeight={fonts.emphasisWeight}
          fontStyle={fonts.emphasisStyle}
          color={BLUE}
          finalArch={28}
          stagger={1.6}
          duration={11}
        />
      </div>
    </div>
  );
};
