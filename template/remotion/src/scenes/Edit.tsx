import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Easing,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {BigWordBehind} from '../lib/BigWordBehind';
import {reframeTransform} from '../lib/reframe';
import {CaptionLayer, type Cue} from '../lib/CaptionLayer';
import {LogoCard} from '../lib/LogoCard';
import {LogoScatter} from '../lib/LogoScatter';
import {sampleTrack, type Track} from '../lib/track';
import {Finish} from '../lib/Finish';
import {SceneTransition} from '../lib/SceneTransition';
import {Asset3D, Hero3D} from '../lib/Sequence3D';
import {C, FONT, lerp, rp} from '../lib/theme';
import {SideBackdrop, SideCards, SIDE, sideAt, sideMask} from '../layouts/Side';
import {ScreenScene} from '../screen/ScreenScene';
import {PAGES} from '../screen/pages';
import {FULLSCREEN_SCENES} from './fullscreen/registry';
import {
  activeReframe,
  activeScene,
  eventsOfType,
  isRotoActive,
  resolveTransform,
  type Plan,
} from '../lib/plan';

export type EditProps = {
  plan: Plan;
  track: Track;
  captions: Cue[];
};

const fill = {width: '100%', height: '100%'} as const;

/** Cards beside a reframed subject. Full even border and a fill tint: never a one-sided accent bar. */
const CardStack: React.FC<{
  cards: {label: string; value: string}[];
  side: 'left' | 'right';
  reveal: number;
}> = ({cards, side, reveal}) => (
  <div
    style={{
      position: 'absolute',
      top: '50%',
      transform: 'translateY(-50%)',
      [side]: '5%',
      display: 'flex',
      flexDirection: 'column',
      gap: 22,
      width: '34%',
    }}
  >
    {cards.map((card, i) => {
      const t = interpolate(reveal, [i * 0.13, i * 0.13 + 0.4], [0, 1], {
        easing: Easing.bezier(0.22, 1, 0.36, 1),
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
      });
      return (
        <div
          key={card.label}
          style={{
            opacity: t,
            transform: `translateY(${(1 - t) * 26}px)`,
            backgroundColor: 'rgba(12,12,14,0.86)',
            border: `1.5px solid ${C.border}`,
            padding: '20px 26px',
            borderRadius: 14,
            fontFamily: FONT,
          }}
        >
          <div style={{fontSize: 22, letterSpacing: 3, color: C.muted, fontWeight: 700, marginBottom: 8}}>{card.label}</div>
          <div style={{fontSize: 52, color: C.text, fontWeight: 800, letterSpacing: -1, fontVariantNumeric: 'tabular-nums'}}>{card.value}</div>
        </div>
      );
    })}
  </div>
);

export const Edit: React.FC<EditProps> = ({plan, track, captions}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const endAt = plan.sourceFrames ?? plan.durationInFrames;

  // Punches, reframes and the side layout resolve to ONE {scale, dx, dy}. The video, everything in
  // world space, the matte and the caption anchors all take it, so nothing drifts apart.
  const punch = resolveTransform(frame, plan, track);
  const side = width > height ? sideAt(plan, track, frame) : null;
  const sp = side?.p ?? 0;
  const state = side
    ? {...punch, scale: lerp(punch.scale, side.target.scale, sp), dx: lerp(punch.dx, side.target.dx, sp), dy: lerp(punch.dy, side.target.dy, sp)}
    : punch;
  const transform = reframeTransform(state, width, height);
  const roto = isRotoActive(plan, frame);
  const reframe = activeReframe(plan, frame);
  const head = sampleTrack(track, frame);
  const scene = activeScene(plan, frame);
  const sceneRanges = eventsOfType(plan, 'scene').map((s) => ({from: s.from, to: s.to}));
  const mask = sideMask(sp, width, side?.e.subject);
  const screen = eventsOfType(plan, 'screen').find((s) => frame >= s.from && frame <= s.to);
  const screenP = screen ? rp(frame, screen.from + 4, 10) * (1 - rp(frame, screen.to - 14, 10)) : 0;
  const heroes = eventsOfType(plan, 'hero3d');
  const assets = eventsOfType(plan, 'asset3d');

  const reveal = interpolate(state.progress, [0.82, 1], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  // Caption box: centred lower third on the talking head; under the subject's half in the side
  // layout (never under or over the card); centred and narrower in the screen scene (clear of the PiP).
  const k = width / 1920;
  const sideCx = (side?.e.subject === 'right' ? 1 - SIDE.faceX : SIDE.faceX) * width;
  const capCx = screenP > 0 ? width / 2 : lerp(width / 2, sideCx, sp);
  const capW = width > height ? (screenP > 0 ? 900 * k : lerp(1240 * k, 900 * k, sp)) : undefined;

  return (
    <AbsoluteFill style={{backgroundColor: '#08080a', overflow: 'hidden'}}>
      {sp > 0 ? <SideBackdrop src={plan.source} p={Math.min(1, sp * 1.6)} endAt={endAt} width={width} height={height} /> : null}

      {/* Layers below share one transform. Each must be its own AbsoluteFill: a statically
          positioned video paints below any absolutely positioned sibling regardless of DOM order,
          which silently puts graphics in front of the matte meant to occlude them. */}
      <AbsoluteFill style={mask ? {WebkitMaskImage: mask, maskImage: mask} : undefined}>
        <AbsoluteFill style={{transform, transformOrigin: '50% 50%'}}>
          <AbsoluteFill>
            <OffthreadVideo src={staticFile(plan.source)} endAt={endAt} style={fill} />
          </AbsoluteFill>

          {/* Sandwich: between the video and the matte, so inside a roto window it passes behind. */}
          {roto ? (
            <AbsoluteFill>
              {eventsOfType(plan, 'scatter').map((sc) => (
                <LogoScatter key={`scatter-${sc.at}`} items={sc.items} at={sc.at} hold={sc.hold} blurRange={plan.defocus?.scatter} />
              ))}
              {eventsOfType(plan, 'bigWord').map((w) => (
                <BigWordBehind
                  key={`${w.text}-${w.at}`}
                  text={w.text}
                  at={w.at}
                  hold={w.hold}
                  lines={w.lines}
                  face={w.face}
                  size={w.size}
                  y={w.y}
                  blur={plan.defocus?.hero}
                  scale={state.scale}
                />
              ))}
            </AbsoluteFill>
          ) : null}
          {heroes.filter((h) => h.behind).map((h) => (
            <Hero3D key={`hero-${h.seq.dir}`} seq={h.seq} x={h.x} y={h.y} w={h.w} h={h.h} />
          ))}
          {assets.filter((a) => a.behind).map((a) => (
            <Asset3D key={`asset-${a.seq.dir}-${a.at}`} seq={a.seq} at={a.at} until={a.until} x={a.x} y={a.y} size={a.size} />
          ))}

          {/* World space, not screen space: these inherit the punch, so they grow and drift outward
              exactly as an object beside the subject would. In screen space they read as stickers. */}
          {eventsOfType(plan, 'logo').map((l) => (
            <LogoCard key={`${l.from}-${l.logos[0]?.src}`} logos={l.logos} from={l.from} to={l.to} side={l.side} x={l.x} y={l.y} />
          ))}

          {roto ? (
            <AbsoluteFill>
              <Img src={staticFile(`${plan.cutDir ?? 'cut'}/frame_${String(Math.min(frame, endAt - 1)).padStart(5, '0')}.png`)} style={fill} />
            </AbsoluteFill>
          ) : null}

          {heroes.filter((h) => !h.behind).map((h) => (
            <Hero3D key={`hero-${h.seq.dir}`} seq={h.seq} x={h.x} y={h.y} w={h.w} h={h.h} />
          ))}
          {assets.filter((a) => !a.behind).map((a) => (
            <Asset3D key={`asset-${a.seq.dir}-${a.at}`} seq={a.seq} at={a.at} until={a.until} x={a.x} y={a.y} size={a.size} />
          ))}
        </AbsoluteFill>
      </AbsoluteFill>

      {sp > 0 ? (
        <AbsoluteFill
          style={{
            background: `linear-gradient(${side?.e.subject === 'right' ? 270 : 90}deg, rgba(0,0,0,0) 48%, rgba(0,0,0,0.28) 72%)`,
            opacity: sp,
          }}
        />
      ) : null}
      {side ? <SideCards e={side.e} f={frame} width={width} height={height} /> : null}

      {reframe?.cards && reveal > 0 ? (
        <CardStack cards={reframe.cards} side={reframe.subjectSide === 'left' ? 'right' : 'left'} reveal={reveal} />
      ) : null}

      {scene
        ? (() => {
            const Comp = FULLSCREEN_SCENES[scene.comp];
            if (!Comp) throw new Error(`Unknown fullscreen comp "${scene.comp}". Registered: ${Object.keys(FULLSCREEN_SCENES).join(', ')}`);
            return (
              <SceneTransition event={scene}>
                <Comp from={scene.from} to={scene.to} props={scene.props ?? {}} />
              </SceneTransition>
            );
          })()
        : null}

      {screen
        ? (() => {
            const Page = PAGES[screen.page];
            if (!Page) throw new Error(`Unknown screen page "${screen.page}". Registered: ${Object.keys(PAGES).join(', ')}`);
            return (
              <AbsoluteFill>
                <ScreenScene
                  cameraSrc={plan.source}
                  cameraEndAt={endAt}
                  url={screen.url}
                  tabTitle={screen.tabTitle}
                  tabIcon={screen.tabIcon}
                  backgroundSrc={screen.backgroundSrc}
                  enterFrame={screen.from}
                  exitFrame={screen.to - 14}
                  zoomKeys={screen.zoom}
                  cursorActions={screen.cursor}
                  cursorTargets={screen.targets}
                >
                  <Page props={screen.props ?? {}} />
                </ScreenScene>
              </AbsoluteFill>
            );
          })()
        : null}

      {eventsOfType(plan, 'sfx').map((e) => (
        <Sequence key={`sfx-${e.at}-${e.src}-${e.reason}`} from={Math.max(0, e.at)} durationInFrames={150} layout="none">
          <Audio src={staticFile(e.src)} volume={e.volume ?? 0.04} />
        </Sequence>
      ))}

      {eventsOfType(plan, 'endcard').map((e) => (
        <React.Fragment key={`endcard-${e.from}`}>
          {/* whole-frame dip to black after the last word, then the card */}
          <AbsoluteFill style={{backgroundColor: '#0a0b0c', opacity: interpolate(frame, [e.from - 4, e.from], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}} />
          <Sequence from={e.from} durationInFrames={e.frames}>
            <AbsoluteFill style={{backgroundColor: '#0a0b0c'}}>
              <OffthreadVideo src={staticFile(e.src)} volume={e.volume ?? 0.36} style={fill} />
            </AbsoluteFill>
          </Sequence>
        </React.Fragment>
      ))}

      {screenP > 0 ? (
        // screen scene only: soft full-width scrim under the caption band (no box, no border)
        <AbsoluteFill
          style={{
            top: height - 260 * k,
            height: 260 * k,
            opacity: screenP,
            background: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,0.42) 45%, rgba(0,0,0,0.7) 100%)',
          }}
        />
      ) : null}

      <CaptionLayer
        cues={captions}
        pairing={plan.captions?.pairing}
        trackedUntil={plan.captions?.trackedUntil ?? 0}
        position={plan.captions?.position}
        avoidTop={eventsOfType(plan, 'bigWord').map((w) => ({from: w.at - 14, to: w.at + w.hold + 14}))}
        fixedDuring={[...sceneRanges, ...eventsOfType(plan, 'screen'), ...eventsOfType(plan, 'side')].map((r) => ({from: r.from, to: r.to}))}
        silence={plan.captions?.silence}
        accent={plan.captions?.accent}
        track={track}
        videoScale={state.scale}
        scaleOrigin={{cx: head.cx, cy: head.cy}}
        cx={capCx}
        boxWidth={capW}
        heavy={screenP}
      />

      {plan.finish ? <Finish grain={plan.finish.grain} vignette={plan.finish.vignette} /> : null}
    </AbsoluteFill>
  );
};
