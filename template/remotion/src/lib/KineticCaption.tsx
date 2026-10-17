// Kinetic captions for the cold open, modelled on the DROPS 41 reference.
//
// What the reference actually does, from a frame by frame read, and what makes
// it work rather than just move:
//   1. Words ACCUMULATE. The phrase builds word by word and stays up until the
//      thought completes, then clears. It is not one card replacing another.
//   2. Two faces in one phrase: plain uppercase sans for the connective words,
//      a display serif for the words that carry the meaning.
//   3. The newest word arrives dim and settles, so the eye is pulled to it.
//   4. Lines are ragged, not a rigid left edge.
//
// Their emphasis face is a pink serif. Ours is Instrument Serif Italic in amber,
// which is already the show's emphasis face in the burned-in captions, so the
// cold open and the rest of the episode read as the same piece.
//
// This REPLACES the bottom caption for its window. Running both would caption
// the same sentence twice.
import React from 'react';
import {Easing, Img, interpolate, staticFile, useCurrentFrame} from 'remotion';

export type KineticWord = {
  w: string;
  at: number;
  emphasis?: boolean;
  /** Basename in public/marks. Pops in behind the word, like a sticker. */
  logo?: string;
};

export type KineticGroup = {from: number; to: number; words: KineticWord[]};

type Props = {
  groups: KineticGroup[];
  side: 'left' | 'right';
  /** Column width in px. Match it to the canvas the reframe opens. */
  column?: number;
  regularFamily: string;
  emphasisFamily: string;
  emphasisWeight: number;
  accent: string;
};

const EASE = Easing.out(Easing.quad);
const IN_FRAMES = 7;
const SETTLE = 9;      // how long a word stays in its "just arrived" grey
const CLEAR = 8;       // fade out at the end of a group

// A fixed ragged indent per line index. Deterministic, so it is identical on
// every render, and small enough to read as hand-set rather than broken.
const INDENT = [0, 38, 14, 52, 26];

export const KineticCaption: React.FC<Props> = ({
  groups,
  side,
  column = 660,
  regularFamily,
  emphasisFamily,
  emphasisWeight,
  accent,
}) => {
  const frame = useCurrentFrame();
  const group = groups.find((g) => frame >= g.from && frame <= g.to + CLEAR);
  if (!group) return null;

  const out = interpolate(frame, [group.to, group.to + CLEAR], [1, 0], {
    easing: EASE,
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const shown = group.words.filter((w) => frame >= w.at);
  const newest = shown.length ? shown[shown.length - 1] : undefined;

  return (
    <>
      {/* The emphasis face is amber and his key light is an amber shelf lamp on
          exactly this side, so the words that matter most were the ones fighting
          the background. A soft directional scrim fixes it without reading as a
          box, and it fades out well before it reaches him. */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          opacity: out,
          background: `linear-gradient(to ${side === 'left' ? 'right' : 'left'}, rgba(8,8,10,0.82) 0%, rgba(8,8,10,0.66) 28%, rgba(8,8,10,0.28) 52%, rgba(8,8,10,0) 72%)`,
          pointerEvents: 'none',
        }}
      />
    <div
      style={{
        position: 'absolute',
        top: 0,
        bottom: 0,
        [side]: 86,
        width: column,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        opacity: out,
        pointerEvents: 'none',
      }}
    >
      <div style={{display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: '0 18px', rowGap: 6}}>
        {group.words.map((word, i) => {
          const p = interpolate(frame, [word.at, word.at + IN_FRAMES], [0, 1], {
            easing: EASE,
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          });
          if (p === 0) return null;
          const isNewest = newest === word && frame < word.at + SETTLE;
          const size = word.emphasis ? 112 : 78;
          return (
            <span
              key={`${word.w}-${i}`}
              style={{
                position: 'relative',
                display: 'inline-flex',
                alignItems: 'center',
                marginLeft: i === 0 ? 0 : INDENT[i % INDENT.length] * 0.28,
                transform: `translateY(${interpolate(p, [0, 1], [14, 0]).toFixed(2)}px)`,
                opacity: p,
              }}
            >
              {word.logo ? (
                // Sits INLINE ahead of the word, not centred behind it. Behind was
                // the first attempt and it fails twice: an amber serif word on top of
                // an orange disc is barely legible, and at a readable disc size the
                // mark is mostly hidden by the word anyway. The reference does this
                // inline too (a brand mark ahead of its name).
                <Img
                  src={staticFile(`marks/${word.logo}`)}
                  style={{
                    width: size * 0.92,
                    height: size * 0.92,
                    marginRight: size * 0.16,
                    transform: `scale(${interpolate(frame, [word.at, word.at + 13], [0.3, 1], {easing: Easing.out(Easing.back(2.2)), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}).toFixed(3)}) rotate(${interpolate(frame, [word.at, word.at + 13], [-26, 0], {easing: Easing.out(Easing.back(2.2)), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}).toFixed(2)}deg)`,
                    filter: 'drop-shadow(0 4px 14px rgba(0,0,0,0.6))',
                  }}
                />
              ) : null}
              <span
                style={{
                  position: 'relative',
                  zIndex: 1,
                  fontFamily: word.emphasis ? emphasisFamily : regularFamily,
                  fontWeight: word.emphasis ? emphasisWeight : 700,
                  fontStyle: word.emphasis ? 'italic' : 'normal',
                  fontSize: size,
                  lineHeight: 1.02,
                  letterSpacing: word.emphasis ? '-0.01em' : '0.01em',
                  textTransform: 'uppercase',
                  color: word.emphasis ? accent : isNewest ? 'rgba(245,243,240,0.42)' : '#F5F3F0',
                  transition: 'none',
                  textShadow: '0 3px 22px rgba(0,0,0,0.75)',
                  WebkitFontSmoothing: 'antialiased',
                }}
              >
                {word.w}
              </span>
            </span>
          );
        })}
      </div>
    </div>
    </>
  );
};
