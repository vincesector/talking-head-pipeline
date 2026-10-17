import React from 'react';
import {useCurrentFrame} from 'remotion';
import {fontPairings, type FontPairingId} from './fontPairings';
import {revealProgress} from './motionCurves';

export type Token = {w: string; e?: boolean};

type Props = {
  tokens: Token[];
  pairing?: FontPairingId;
  fontSize?: number;
  /**
   * Emphasis colour. Pick it against YOUR set: measure the background hue, and
   * if the room is warm (most lamps are) a warm accent goes muddy on it; the
   * complement pops. Swap this one value when the accent should feel native.
   */
  accent?: string;
};

/**
 * Running captions carrying the research pairing, with per-word emphasis.
 *
 * The research effects (Wiggle, Reveal, Arched) are two-line title cards built
 * for a 1080x1920 frame. Across 86 seconds of talking they are exhausting and
 * they cannot mark a single word inside a phrase. This keeps what transfers,
 * the font pairing, the reveal curve and the colour logic, and drops the
 * card layout.
 */
export const RunningCaption: React.FC<Props> = ({
  tokens,
  pairing = 'helvetica-instrument',
  fontSize = 62,
  accent = '#7AA2FF',
}) => {
  const frame = useCurrentFrame();
  const fonts = fontPairings[pairing];

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'center',
        alignItems: 'baseline',
        gap: `0 ${fontSize * 0.26}px`,
        width: '100%',
      }}
    >
      {tokens.map((token, i) => {
        // 1.5-frame stagger. Fast enough to keep up with speech, slow enough
        // that the line does not arrive as one block.
        const t = revealProgress(frame, i * 1.5, 7);
        const emphasis = Boolean(token.e);
        return (
          <span
            key={`${token.w}-${i}`}
            style={{
              display: 'inline-block',
              opacity: t,
              transform: `translateY(${(1 - t) * 14}px)`,
              fontFamily: emphasis ? fonts.emphasisFamily : fonts.baseFamily,
              fontWeight: emphasis ? fonts.emphasisWeight : fonts.baseWeight,
              fontStyle: emphasis ? fonts.emphasisStyle : 'normal',
              color: emphasis ? accent : '#ffffff',
              // HARD RULE: an emphasis word changes face AND grows. 1.12 read as a font swap
              // rather than emphasis. 1.22 is noticeable without being a title card.
              // Baseline alignment on the row means it grows upward and the line stays put.
              fontSize: emphasis ? fontSize * 1.22 : fontSize,
              letterSpacing: emphasis ? 0 : -0.5,
            }}
          >
            {token.w}
          </span>
        );
      })}
    </div>
  );
};
