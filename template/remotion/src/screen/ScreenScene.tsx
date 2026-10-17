import React from 'react';
import {AbsoluteFill, Easing, Img, interpolate, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {C, FONT} from '../lib/theme';

/**
 * SCREEN scene (16:9): a browser window holding whatever page you build, with the presenter's
 * camera shrinking into a rounded picture-in-picture, an animated cursor and camera zooms.
 *
 *   +------------------------------------------------+
 *   |  +------------------------------------------+  |
 *   |  | o o o  [ tab ]                           |  |
 *   |  | < > C  [ your.url/here               ]   |  |
 *   |  |                                          |  |
 *   |  |   children: the page (slot)              |  |
 *   |  |                          +-----------+   |  |
 *   |  |                          |   PiP     |   |  |
 *   |  +--------------------------|  camera   |---+  |
 *   |   captions, centred, clear  +-----------+      |
 *   +------------------------------------------------+
 *
 * Built in a 1920x1080 design space and scaled to the composition. The camera shrinks over 14
 * frames on entry and grows back on exit. Zoom keys and cursor targets are in that design space.
 */
const DW = 1920;
const DH = 1080;
export const BROWSER = {x: 81, y: 44, width: 1698, height: 970};
export const PIP = {x: 1502, y: 676, width: 384, height: 372};
const ease = Easing.inOut(Easing.cubic);
const clampX = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

export type Point = {x: number; y: number};
export type CursorAction = {at: number; to: string | Point; click?: boolean};
/** Arrive at this camera state ON frame `at` (a word), moving over `dur` frames (default 16) from the previous one. */
export type ZoomKey = {at: number; scale: number; x: number; y: number; dur?: number};

const mix = (a: number, b: number, t: number) => a + (b - a) * t;
const prog = (frame: number, from: number, to: number) => interpolate(frame, [from, to], [0, 1], {...clampX, easing: ease});

/** Camera at a frame: starts at rest (whole page), each key is reached on its own word. */
export const zoomAt = (frame: number, keys: ZoomKey[]) => {
  let state = {scale: 1, x: DW / 2, y: DH / 2};
  for (const k of [...keys].sort((a, b) => a.at - b.at)) {
    const start = k.at - (k.dur ?? 16);
    if (frame >= k.at) {
      state = {scale: k.scale, x: k.x, y: k.y};
      continue;
    }
    if (frame > start) {
      const t = prog(frame, start, k.at);
      state = {scale: mix(state.scale, k.scale, t), x: mix(state.x, k.x, t), y: mix(state.y, k.y, t)};
    }
    break;
  }
  return state;
};

export const mapThroughZoom = (p: Point, z: {scale: number; x: number; y: number}): Point => ({
  x: DW / 2 + (p.x - z.x) * z.scale,
  y: DH / 2 + (p.y - z.y) * z.scale,
});

const BrowserChrome: React.FC<{url: string; title: string; icon: string; children: React.ReactNode}> = ({url, title, icon, children}) => (
  <div
    style={{
      position: 'absolute',
      left: BROWSER.x,
      top: BROWSER.y,
      width: BROWSER.width,
      height: BROWSER.height,
      borderRadius: 15,
      overflow: 'hidden',
      background: '#0b0e10',
      boxShadow: '0 34px 85px rgba(0,0,0,.54), 0 0 0 1px rgba(255,255,255,.12)',
      fontFamily: FONT,
      color: '#d8d9da',
      textRendering: 'geometricPrecision',
    }}
  >
    <div style={{height: 40, background: '#26272d', display: 'flex', alignItems: 'end', paddingLeft: 17}}>
      <div style={{display: 'flex', gap: 7, marginBottom: 15, marginRight: 22}}>
        {['#ff6159', '#ffbf2f', '#29c940'].map((color) => (
          <i key={color} style={{width: 11, height: 11, borderRadius: '50%', background: color, display: 'block'}} />
        ))}
      </div>
      <div style={{width: 193, height: 34, borderRadius: '8px 8px 0 0', background: '#35363b', display: 'flex', alignItems: 'center', gap: 11, padding: '0 13px', boxSizing: 'border-box', fontSize: 13}}>
        <span style={{width: 17, height: 17, background: C.accent, color: '#1a1206', borderRadius: 3, textAlign: 'center', lineHeight: '17px', fontSize: 12, fontWeight: 800}}>{icon}</span>
        <span style={{flex: 1, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis'}}>{title}</span>
        <span style={{color: '#aaaeb2', fontSize: 14}}>×</span>
      </div>
      <span style={{fontSize: 22, lineHeight: '34px', paddingLeft: 12, color: '#9ea0a5'}}>+</span>
    </div>
    <div style={{height: 42, background: '#303137', display: 'flex', alignItems: 'center', gap: 15, padding: '0 16px', boxSizing: 'border-box', fontSize: 19}}>
      <span style={{color: '#93969d'}}>‹</span>
      <span style={{color: '#93969d'}}>›</span>
      <span style={{color: '#93969d', fontSize: 17}}>⟳</span>
      <div style={{height: 28, marginLeft: 12, flex: 1, borderRadius: 7, background: '#202126', display: 'flex', alignItems: 'center', padding: '0 14px', fontSize: 12, color: '#b9bbc0'}}>
        <span style={{fontSize: 10, paddingRight: 8}}>◈</span>
        {url}
      </div>
      <span style={{fontSize: 16, color: '#aaaeb2'}}>☰</span>
    </div>
    <div style={{height: BROWSER.height - 82, overflow: 'hidden', position: 'relative'}}>{children}</div>
  </div>
);

const resolvePoint = (to: string | Point, targets: Record<string, Point>): Point =>
  typeof to === 'string' ? (targets[to] ?? {x: DW / 2, y: DH / 2}) : to;

const cursorAt = (frame: number, actions: CursorAction[], targets: Record<string, Point>): Point => {
  if (!actions.length) return {x: DW / 2, y: DH / 2};
  let previous: CursorAction = {at: actions[0].at - 16, to: {x: 580, y: 650}};
  for (const action of actions) {
    const target = resolvePoint(action.to, targets);
    const origin = resolvePoint(previous.to, targets);
    if (frame <= action.at) {
      const t = prog(frame, Math.max(previous.at, action.at - 16), action.at);
      return {x: mix(origin.x, target.x, t), y: mix(origin.y, target.y, t)};
    }
    previous = action;
  }
  return resolvePoint(actions[actions.length - 1].to, targets);
};

/** Arrow cursor that glides between targets (16 frames, eased) and pulses a ring on each click. */
export const ScreenCursor: React.FC<{actions: CursorAction[]; targets: Record<string, Point>; zoom: {scale: number; x: number; y: number}; visible: boolean}> = ({
  actions,
  targets,
  zoom,
  visible,
}) => {
  const frame = useCurrentFrame();
  if (!visible) return null;
  const pos = mapThroughZoom(cursorAt(frame, actions, targets), zoom);
  const click = actions.find((a) => a.click && frame >= a.at && frame <= a.at + 12);
  const cp = click ? mapThroughZoom(resolvePoint(click.to, targets), zoom) : null;
  const age = click ? frame - click.at : 0;
  const press = click && age <= 3 ? interpolate(age, [0, 2, 3], [1, 0.83, 1], clampX) : 1;
  return (
    <>
      {cp && (
        <div style={{position: 'absolute', left: cp.x, top: cp.y, width: 34 + age * 2, height: 34 + age * 2, borderRadius: '50%', border: '2px solid rgba(255,255,255,.75)', transform: 'translate(-50%,-50%)', opacity: 1 - age / 12}} />
      )}
      <svg width="31" height="39" viewBox="0 0 31 39" style={{position: 'absolute', left: pos.x, top: pos.y, transform: `scale(${press})`, filter: 'drop-shadow(1px 2px 2px #000)'}}>
        <path d="M2 1 L2 29 L9.3 23.4 L14.7 36 L20.3 33.8 L14.5 21.8 L24.4 21.5 Z" fill="white" stroke="#111" strokeWidth="2.1" strokeLinejoin="round" />
      </svg>
    </>
  );
};

export type ScreenSceneProps = {
  /** The presenter's footage (staticFile path), plays in sync with the composition. */
  cameraSrc: string;
  url?: string;
  tabTitle?: string;
  tabIcon?: string;
  /** Optional backdrop image in public/ (calm and dark). Default: a dark gradient. */
  backgroundSrc?: string;
  enterFrame: number;
  exitFrame: number;
  cameraEndAt?: number;
  zoomKeys?: ZoomKey[];
  cursorActions?: CursorAction[];
  cursorTargets?: Record<string, Point>;
  pipBox?: {x: number; y: number; width: number; height: number};
  children: React.ReactNode;
};

export const ScreenScene: React.FC<ScreenSceneProps> = ({
  cameraSrc,
  url = 'example.com',
  tabTitle = 'Example',
  tabIcon = 'E',
  backgroundSrc,
  enterFrame,
  exitFrame,
  cameraEndAt,
  zoomKeys = [],
  cursorActions = [],
  cursorTargets = {},
  pipBox = PIP,
  children,
}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const k = Math.min(width / DW, height / DH);
  const pip = prog(frame, enterFrame, enterFrame + 14) * (1 - prog(frame, exitFrame, exitFrame + 14));
  const zoom = zoomAt(frame, zoomKeys);
  const cam = {
    x: mix(0, pipBox.x, pip),
    y: mix(0, pipBox.y, pip),
    width: mix(DW, pipBox.width, pip),
    height: mix(DH, pipBox.height, pip),
  };
  return (
    <AbsoluteFill style={{background: '#0c0e10', overflow: 'hidden'}}>
      <div style={{position: 'absolute', left: (width - DW * k) / 2, top: (height - DH * k) / 2, width: DW, height: DH, transform: `scale(${k})`, transformOrigin: '0 0', overflow: 'hidden'}}>
        {backgroundSrc ? (
          <Img src={staticFile(backgroundSrc)} style={{position: 'absolute', width: DW, height: DH, objectFit: 'cover'}} />
        ) : (
          <AbsoluteFill style={{background: 'radial-gradient(80% 90% at 30% 20%, #1d2228 0%, #0c0e10 70%)'}} />
        )}
        <AbsoluteFill style={{background: 'rgba(0,0,0,.15)'}} />
        <div style={{position: 'absolute', width: DW, height: DH, transform: `translate(${DW / 2}px, ${DH / 2}px) scale(${zoom.scale}) translate(${-zoom.x}px, ${-zoom.y}px)`, transformOrigin: '0 0'}}>
          <BrowserChrome url={url} title={tabTitle} icon={tabIcon}>
            {children}
          </BrowserChrome>
        </div>
        <ScreenCursor actions={cursorActions} targets={cursorTargets} zoom={zoom} visible={frame >= enterFrame + 17 && frame < exitFrame - 5} />
        <div
          style={{
            position: 'absolute',
            left: cam.x,
            top: cam.y,
            width: cam.width,
            height: cam.height,
            borderRadius: mix(0, 28, pip),
            overflow: 'hidden',
            boxShadow: pip > 0 ? `0 18px 55px rgba(0,0,0,${0.35 * pip})` : undefined,
            zIndex: 5,
          }}
        >
          <OffthreadVideo
            src={staticFile(cameraSrc)}
            muted
            endAt={cameraEndAt}
            style={{width: '100%', height: '100%', objectFit: 'cover', objectPosition: `${mix(50, 52, pip)}% ${mix(50, 30, pip)}%`}}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};
