import {Easing, interpolate} from 'remotion';
import {loadFont as loadInter} from '@remotion/google-fonts/Inter';

/**
 * Neutral design tokens for cards, screen scenes and stages. Re-skin a whole video by editing this
 * file: every new component reads its colours, font and curves from here.
 */
const inter = loadInter('normal', {weights: ['400', '500', '600', '700', '800'], subsets: ['latin']});
export const FONT = inter.fontFamily;

export const C = {
  bg: '#0b0c0e',
  panel: '#121417',
  panelHi: '#181b1f',
  border: '#2a2e33',
  text: '#eceef0',
  muted: '#a3a9b0',
  dim: '#6b7178',
  accent: '#ffb35c',
  accentBg: 'rgba(255,179,92,0.13)',
  positive: '#3ddc97',
  positiveBg: 'rgba(61,220,151,0.13)',
  negative: '#ff5c6d',
  negativeBg: 'rgba(255,92,109,0.13)',
};

/**
 * Curves. HARD RULE: every move eases at both ends and nothing attacks in under ~12 frames.
 * Quadratic in/out for pushes (no mid-move snap), a gentler sine for releases.
 */
export const camIn = Easing.inOut(Easing.quad);
export const camOut = Easing.inOut(Easing.sin);
export const appEase = Easing.bezier(0.16, 1, 0.3, 1);
export const enterEase = Easing.bezier(0.22, 1, 0.36, 1);

export const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

/** 0 -> 1 from `start` over `dur` frames. */
export const rp = (f: number, start: number, dur: number, ease: (t: number) => number = appEase) =>
  interpolate(f, [start, start + dur], [0, 1], {...clamp, easing: ease});
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
