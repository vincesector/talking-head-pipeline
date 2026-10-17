import React from 'react';
import {AbsoluteFill, OffthreadVideo, staticFile} from 'remotion';
import type {Plan, SideEvent} from '../lib/plan';
import {eventsOfType} from '../lib/plan';
import {sampleTrack, type Track} from '../lib/track';
import {camIn, camOut, lerp, rp} from '../lib/theme';
import {cardPunch} from '../lib/Panel';
import {CARDS} from './cards';

/**
 * SIDE layout (16:9): the presenter slides to one side and a content-sized card sits on the other.
 *
 *   +-----------------------------------------------+
 *   |            .                                  |
 *   |   (face)   .        +-------------------+     |
 *   |   at 0.29W .        |  card, sized to   |     |
 *   |   scale    .        |  its content,     |     |
 *   |   ~1.18    .        |  centred 0.727W   |     |
 *   |            .        +-------------------+     |
 *   |  caption under the presenter's half           |
 *   +-----------------------------------------------+
 *
 * The room the presenter no longer covers is filled with the same footage, blurred and darkened,
 * and the slid footage feathers into it on the card side. No letterbox, no browser frame.
 * Fractions are of the composition, measured on a 1920x1080 layout that shipped.
 */
export const SIDE = {scale: 1.18, faceX: 0.2917, cardX: 0.7266, cardY: 0.45, inLead: 8, inDur: 16, outDur: 16};

/** How far into the side layout we are (0..1), the event, and the presenter's locked target transform. */
export const sideAt = (plan: Plan, track: Track, f: number) => {
  for (const e of eventsOfType(plan, 'side')) {
    const a = e.from - SIDE.inLead;
    if (f < a || f > e.to + SIDE.outDur) continue;
    const p = rp(f, a, SIDE.inDur, camIn) * (1 - rp(f, e.to, SIDE.outDur, camOut));
    // Lock to the face on the entry frame: recomputing per frame makes the camera chase the subject.
    const face = sampleTrack(track, e.from);
    const s = e.scale ?? SIDE.scale;
    const tx = e.subject === 'right' ? 1 - SIDE.faceX : SIDE.faceX;
    const dx = tx - 0.5 - (face.cx - 0.5) * s;
    const dy = (face.cy - 0.5) * (1 - s);
    return {p, e, target: {scale: s, dx, dy}};
  }
  return null;
};

/** The presenter's own room, blurred and darkened, under the slid footage. */
export const SideBackdrop: React.FC<{src: string; p: number; endAt: number; width: number; height: number}> = ({src, p, endAt, width, height}) => (
  <AbsoluteFill style={{opacity: p, overflow: 'hidden'}}>
    {/* rendered at a quarter size and scaled up: the blur hides it and it renders 16x cheaper */}
    <div
      style={{
        position: 'absolute',
        left: -width * 0.05,
        top: -height * 0.05,
        width: width * 0.275,
        height: height * 0.275,
        transform: 'scale(4)',
        transformOrigin: '0 0',
        filter: 'blur(7px) brightness(0.42) saturate(0.85)',
      }}
    >
      <OffthreadVideo src={staticFile(src)} endAt={endAt} muted style={{width: '100%', height: '100%'}} />
    </div>
  </AbsoluteFill>
);

/** CSS mask that feathers the slid footage into the backdrop on the card side. */
export const sideMask = (p: number, width: number, subject: 'left' | 'right' = 'left') => {
  if (p <= 0.001) return undefined;
  const k = width / 1920;
  const a = lerp(2600, 1020, p) * k;
  const b = lerp(3000, 1520, p) * k;
  return `linear-gradient(${subject === 'right' ? 270 : 90}deg, #000 0px, #000 ${a}px, transparent ${b}px)`;
};

/** The card column: cards swap on their words (`at`), punch on the numbers they name. */
export const SideCards: React.FC<{e: SideEvent; f: number; width: number; height: number}> = ({e, f, width, height}) => {
  const enter = rp(f, e.from - SIDE.inLead, SIDE.inDur);
  const exit = rp(f, e.to, SIDE.outDur, camOut);
  const cx = (e.subject === 'right' ? 1 - SIDE.cardX : SIDE.cardX) * width;
  const cy = SIDE.cardY * height;
  const dir = e.subject === 'right' ? -1 : 1;
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      {e.cards.map((c, i) => {
        const spec = CARDS[c.kind];
        if (!spec) throw new Error(`unknown card kind "${c.kind}". Registered: ${Object.keys(CARDS).join(', ')}`);
        const props = c.props ?? {};
        const {w, h} = spec.size(props);
        const next = e.cards[i + 1];
        const cin = i === 0 ? enter : rp(f, c.at - 6, 16);
        const cout = next ? rp(f, next.at - 8, 12, camOut) : exit;
        const o = cin * (1 - cout);
        if (o <= 0.001) return null;
        const pk = cardPunch(f, c.punches);
        const slide = dir * ((1 - cin) * 70 + (next ? -40 * cout : 70 * cout));
        return (
          <div
            key={`${c.kind}-${c.at}`}
            style={{
              position: 'absolute',
              left: cx - w / 2,
              top: cy - h / 2,
              width: w,
              opacity: o,
              transform: `translateX(${slide}px) scale(${(0.97 + 0.03 * Math.min(cin, 1 - (next ? cout : 0))) * pk.s})`,
              transformOrigin: `${pk.ox * w}px ${pk.oy * h}px`,
            }}
          >
            {spec.render(f, props, c.at)}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
