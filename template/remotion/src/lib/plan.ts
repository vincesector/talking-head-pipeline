import type {DisplayFaceId} from './displayFaces';
import type {LogoSpec} from './LogoCard';
import type {ScatterItem} from './LogoScatter';
import type {FontPairingId} from './fontPairings';
import {punchScale, type PunchPreset} from './punchIn';
import {reframeAt, type ReframeShot, type ReframeState} from './reframe';
import {sampleTrack, type Track} from './track';
import type {Seq3D} from './Sequence3D';
import type {CardPunch} from './Panel';
import type {CursorAction, Point, ZoomKey} from '../screen/ScreenScene';

export type PunchEvent = {
  type: 'punch';
  at: number;
  hold: number;
  preset?: PunchPreset;
  scale?: number;
  reason?: string;
};

export type ReframeEvent = {
  type: 'reframe';
  at: number;
  hold: number;
  subjectSide: 'left' | 'right';
  targetX?: number;
  scale?: number | null;
  cards?: {label: string; value: string}[];
  reason?: string;
};

export type RotoEvent = {type: 'roto'; from: number; to: number; reason?: string};

export type BigWordEvent = {
  type: 'bigWord';
  at: number;
  hold: number;
  text: string;
  /** Explicit line breaks, e.g. ['NOT','AMERICAN']. Stacked lines go bigger. */
  lines?: string[];
  /** Tall condensed face. Defaults to anton. See displayFaces.ts */
  face?: DisplayFaceId;
  /** Cap height as a fraction of frame height. Defaults to 0.8. */
  size?: number;
  /** Vertical nudge, fraction of frame height. Negative is up. */
  y?: number;
  reason?: string;
};

export type ScatterEvent = {
  type: 'scatter';
  at: number;
  hold: number;
  items: ScatterItem[];
  reason?: string;
};

export type LogoEvent = {
  type: 'logo';
  from: number;
  to: number;
  logos: LogoSpec[];
  side?: 'left' | 'right';
  /** Horizontal centre, normalized. Defaults to the measured gap centre. */
  x?: number;
  y?: number;
  reason?: string;
};

export type SceneEvent = {
  type: 'scene';
  from: number;
  to: number;
  /** Key in scenes/fullscreen/registry.ts. */
  comp: string;
  /** Handed straight to the scene component. Shape is per comp. */
  props?: Record<string, unknown>;
  /**
   * Boundary treatment. Defaults to 'fadeblur' (fade + blur). There is deliberately no zigzag /
   * jagged-teeth shutter: it looks cheesy and cheapens good animation.
   */
  transition?: 'fadeblur' | 'fade';
  /** Frames spent on each of the in and out transitions, inside [from, to]. Defaults to 10. */
  transitionFrames?: number;
  reason?: string;
};

/** A sound effect. `at` is the frame the file STARTS; fire it at beat - (file peak time) so its
 * loudest moment lands on the beat (most library files have a build before the peak). */
export type SfxEvent = {
  type: 'sfx';
  at: number;
  src: string;
  volume?: number;
  reason?: string;
};

/** 3D hero type: a transparent PNG sequence from tools/render3d placed in world space. Box = centre x/y, w/h in comp px.
 * `at` / `until` are the entry and exit words (the shot's `in` / `out` must be the same frames; the renderer animates).
 * `behind: true` draws it under the matte, so inside a roto window it passes behind the subject. */
export type Hero3DEvent = {
  type: 'hero3d';
  at: number;
  until: number;
  seq: Seq3D;
  x: number;
  y: number;
  w: number;
  h: number;
  behind?: boolean;
  reason?: string;
};

/** A rendered 3D object (logo, icon, medallion) beside the subject, arriving on `at`, leaving from `until`. */
export type Asset3DEvent = {
  type: 'asset3d';
  at: number;
  until: number;
  seq: Seq3D;
  x: number;
  y: number;
  size: number;
  behind?: boolean;
  reason?: string;
};

export type SideCard = {kind: string; at: number; props?: Record<string, unknown>; punches?: CardPunch[]};
/** SIDE layout: the subject slides to one side, content-sized cards sit on the other and swap on their `at`. */
export type SideEvent = {type: 'side'; from: number; to: number; subject?: 'left' | 'right'; scale?: number; cards: SideCard[]; reason?: string};

/** SCREEN scene: browser window with a page from screen/pages.tsx, camera shrinks into a PiP. Coordinates in 1920x1080 design px. */
export type ScreenEvent = {
  type: 'screen';
  from: number;
  to: number;
  page: string;
  props?: Record<string, unknown>;
  url?: string;
  tabTitle?: string;
  tabIcon?: string;
  backgroundSrc?: string;
  zoom?: ZoomKey[];
  cursor?: CursorAction[];
  targets?: Record<string, Point>;
  reason?: string;
};

/** End card after the last word: whole-frame dip to black, then a clip (its own audio at `volume`). */
export type EndcardEvent = {type: 'endcard'; from: number; src: string; frames: number; volume?: number; reason?: string};

export type EditEvent =
  | PunchEvent
  | ReframeEvent
  | RotoEvent
  | BigWordEvent
  | LogoEvent
  | ScatterEvent
  | SceneEvent
  | SfxEvent
  | Hero3DEvent
  | Asset3DEvent
  | SideEvent
  | ScreenEvent
  | EndcardEvent;

export type Plan = {
  source: string;
  fps: number;
  width: number;
  height: number;
  durationInFrames: number;
  /** Frames of the source video, when the composition runs past it (an end card). */
  sourceFrames?: number;
  zoomHeadroom: number;
  /**
   * Defocus for sandwiched graphics, in PIXELS at this comp's resolution.
   *
   * Not a constant: between a 23mm f2.5 and an 85mm f1.4 the background
   * separation changes enormously. Set it per
   * clip from the lens table in references/effects.md. Omit and the layout
   * profile's fallback is used, which is a guess.
   */
  defocus?: {hero: number; scatter: [number, number]};
  /** Folder under public/ holding the matte PNG sequence. Defaults to 'cut'. */
  cutDir?: string;
  /** Final-pass grade. Opacities 0 to 1. Omit a key, or the whole object, for none. */
  finish?: {grain?: number; vignette?: number};
  captions?: {
    pairing?: FontPairingId;
    /** Frames before this get head-tracked captions; after, fixed bottom. */
    trackedUntil?: number;
    position?: number;
    accent?: string;
    /** Frame ranges where no caption renders at all, e.g. screenshare with no head to caption over. */
    silence?: {from: number; to: number}[];
  };
  events: EditEvent[];
};

export const eventsOfType = <T extends EditEvent['type']>(
  plan: Plan,
  type: T,
): Extract<EditEvent, {type: T}>[] =>
  plan.events.filter((e) => e.type === type) as Extract<EditEvent, {type: T}>[];

export const isRotoActive = (plan: Plan, frame: number): boolean =>
  eventsOfType(plan, 'roto').some((r) => frame >= r.from && frame <= r.to);

export const activeScene = (plan: Plan, frame: number): SceneEvent | undefined =>
  eventsOfType(plan, 'scene').find((s) => frame >= s.from && frame <= s.to);

export const activeReframe = (
  plan: Plan,
  frame: number,
): ReframeEvent | undefined =>
  eventsOfType(plan, 'reframe').find((r) => {
    const inF = 14;
    const outF = 18;
    return frame >= r.at - inF && frame <= r.at + r.hold + outF;
  });

const IDENTITY: ReframeState = {
  scale: 1,
  dx: 0,
  dy: 0,
  progress: 0,
  clamped: false,
};

/**
 * One transform for the whole stack, whichever effect is driving it.
 *
 * A punch scales about the tracked face, a reframe uses translate+scale about
 * the centre. Expressing both as {scale, dx, dy} means the video, the sandwiched
 * graphics, the matte and the caption anchors all take the identical transform,
 * so nothing can drift relative to anything else.
 *
 * Converting a face-anchored scale to the centre form:
 *   scaling about origin ox maps fx -> fx*s + ox*(1-s)
 *   translate+scale maps  fx -> fx*s + 0.5*(1-s) + dx
 * therefore dx = (ox - 0.5) * (1 - s).
 */
export const resolveTransform = (
  frame: number,
  plan: Plan,
  track: Track,
): ReframeState => {
  const reframe = activeReframe(plan, frame);
  if (reframe) {
    const shot: ReframeShot = {
      at: reframe.at,
      hold: reframe.hold,
      subjectSide: reframe.subjectSide,
      targetX: reframe.targetX,
      scale: reframe.scale ?? undefined,
    };
    return reframeAt(frame, [shot], track);
  }

  const punches = eventsOfType(plan, 'punch').map((p) => ({
    at: p.at,
    hold: p.hold,
    preset: p.preset,
    scale: p.scale,
  }));
  const scale = punchScale(frame, punches);
  if (scale === 1) {
    return IDENTITY;
  }

  const face = sampleTrack(track, frame);
  return {
    scale,
    dx: (face.cx - 0.5) * (1 - scale),
    dy: (face.cy - 0.5) * (1 - scale),
    progress: 0,
    clamped: false,
  };
};
