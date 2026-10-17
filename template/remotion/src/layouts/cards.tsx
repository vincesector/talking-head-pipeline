import React from 'react';
import {Img, staticFile} from 'remotion';
import {Panel} from '../lib/Panel';
import {C, rp} from '../lib/theme';

/**
 * Side-layout cards. A card is sized to its content (no empty bands) and every number on it must be
 * a number the speaker says or a sourced fact: never invent one to fill a card.
 *
 * Add a kind: write {size, render} below and use it from plan.json as
 *   {"kind": "stat", "at": 812, "props": {...}, "punches": [{"at": 830, "until": 870}]}
 * `render(f, props, at)` gets the absolute frame and the card's entry frame; reveal sub-parts on
 * their own words by passing frames in props (e.g. "revealAt": [820, 845]).
 */
export type CardSpec = {
  size: (p: Record<string, unknown>) => {w: number; h: number};
  render: (f: number, p: Record<string, unknown>, at: number) => React.ReactNode;
};

const str = (v: unknown, d = '') => (typeof v === 'string' ? v : d);
const nums = (v: unknown) => (Array.isArray(v) ? (v as number[]) : []);
const tone = (t: unknown) => (t === 'positive' ? C.positive : t === 'negative' ? C.negative : t === 'accent' ? C.accent : C.text);

const Label: React.FC<{children: React.ReactNode}> = ({children}) => (
  <div style={{fontSize: 22, letterSpacing: '0.14em', textTransform: 'uppercase', fontWeight: 600, color: C.muted}}>{children}</div>
);

export const CARDS: Record<string, CardSpec> = {
  /** One big number with a label and an optional line under it. */
  stat: {
    size: (p) => ({w: (p.w as number) ?? 620, h: p.sub ? 300 : 236}),
    render: (_f, p) => (
      <Panel w={(p.w as number) ?? 620}>
        <Label>{str(p.label)}</Label>
        <div style={{fontSize: 104, fontWeight: 800, letterSpacing: '-0.02em', marginTop: 14, color: tone(p.tone)}}>{str(p.value)}</div>
        {p.sub ? <div style={{fontSize: 26, color: C.muted, marginTop: 10}}>{str(p.sub)}</div> : null}
      </Panel>
    ),
  },
  /** A titled list; each item grows in on its own word (`revealAt`, absolute frames). */
  list: {
    size: (p) => ({w: (p.w as number) ?? 680, h: 120 + 78 * ((p.items as string[]) ?? []).length}),
    render: (f, p, at) => {
      const items = (p.items as string[]) ?? [];
      const ra = nums(p.revealAt);
      return (
        <Panel w={(p.w as number) ?? 680}>
          <Label>{str(p.title)}</Label>
          <div style={{marginTop: 18}}>
            {items.map((it, i) => {
              const o = rp(f, (ra[i] ?? at + i * 8) - 8, 12);
              return (
                <div key={it} style={{height: 78 * o, overflow: 'hidden'}}>
                  <div style={{display: 'flex', alignItems: 'center', gap: 18, height: 78, opacity: o, transform: `translateY(${(1 - o) * 10}px)`}}>
                    <div style={{width: 12, height: 12, borderRadius: 6, background: C.accent, flexShrink: 0}} />
                    <div style={{fontSize: 36, fontWeight: 600}}>{it}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </Panel>
      );
    },
  },
  /** Two columns compared row by row (e.g. before / after). Rows reveal on `revealAt`. */
  compare: {
    size: (p) => ({w: (p.w as number) ?? 760, h: 170 + 72 * ((p.rows as unknown[]) ?? []).length}),
    render: (f, p, at) => {
      const rows = (p.rows as {label: string; a: string; b: string}[]) ?? [];
      const [ha, hb] = (p.headers as string[]) ?? ['A', 'B'];
      const ra = nums(p.revealAt);
      const cell: React.CSSProperties = {width: 190, textAlign: 'right', fontSize: 34, fontWeight: 700};
      return (
        <Panel w={(p.w as number) ?? 760}>
          <Label>{str(p.title)}</Label>
          <div style={{display: 'flex', marginTop: 22, color: C.muted, fontSize: 22, fontWeight: 600}}>
            <div style={{flex: 1}} />
            <div style={{...cell, fontSize: 22, color: C.muted}}>{ha}</div>
            <div style={{...cell, fontSize: 22, color: C.accent}}>{hb}</div>
          </div>
          {rows.map((r, i) => {
            const o = rp(f, (ra[i] ?? at + i * 8) - 8, 12);
            return (
              <div key={r.label} style={{display: 'flex', alignItems: 'baseline', height: 72, borderTop: `1px solid ${C.border}`, opacity: o}}>
                <div style={{flex: 1, fontSize: 30, color: C.muted, paddingTop: 18}}>{r.label}</div>
                <div style={{...cell, color: C.text}}>{r.a}</div>
                <div style={{...cell, color: C.accent}}>{r.b}</div>
              </div>
            );
          })}
        </Panel>
      );
    },
  },
  /** A screenshot or still from public/, rounded. Prefer rebuilding UI in code for anything you zoom into. */
  image: {
    size: (p) => ({w: (p.w as number) ?? 720, h: ((p.h as number) ?? 450) + (p.caption ? 64 : 0)}),
    render: (_f, p) => (
      <Panel w={(p.w as number) ?? 720} pad={0}>
        <Img src={staticFile(str(p.src))} style={{display: 'block', width: '100%', height: (p.h as number) ?? 450, objectFit: 'cover'}} />
        {p.caption ? <div style={{padding: '16px 24px', fontSize: 24, color: C.muted}}>{str(p.caption)}</div> : null}
      </Panel>
    ),
  },
};
