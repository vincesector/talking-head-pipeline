// Data-driven port of DepthPoc: a full-screen R3F depth scene driven entirely by
// plan-authored layers and camera stops. Same texture-loading and gating story as
// the proof of concept (delayRender/continueRender, not useLoader/Suspense), just
// parameterised instead of hardcoded so any plan can point it at different assets.
import React, {useEffect, useState} from 'react';
import {
  AbsoluteFill,
  Easing,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  delayRender,
  continueRender,
} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import {useThree} from '@react-three/fiber';
import * as THREE from 'three';
import type {FullscreenSceneProps} from './registry';
import {ParticleField, type ParticleFieldProps} from '../../lib/ParticleField';

type Vec3 = [number, number, number];
type Layer = {src: string; pos: Vec3; w: number; h: number};
type CameraStop = {at: number; pos: Vec3; look?: Vec3};

export type DepthProps = {
  bg?: string;
  /** Textured backdrop behind the cutouts: cover-fit image drifting by `drift`, a ParticleField, a grain overlay. Flat black reads as assets pasted on nothing. */
  backdrop?: {image?: string; drift?: number; particles?: ParticleFieldProps; grain?: number};
  layers: Layer[];
  camera: {fov?: number; stops: CameraStop[]};
  /** Per-layer idle yaw/pitch amplitude in radians. Default 0.03. 0 disables. */
  idle?: number;
};

const useCutout = (url: string): THREE.Texture | null => {
  const [tex, setTex] = useState<THREE.Texture | null>(null);
  const [handle] = useState(() => delayRender(`depth-scene-tex-${url}`));
  useEffect(() => {
    new THREE.TextureLoader().load(
      staticFile(url),
      (t) => {
        t.colorSpace = THREE.SRGBColorSpace;
        setTex(t);
        continueRender(handle);
      },
      undefined,
      (err) => {
        // A missing texture renders as an empty plane with no error otherwise. Say so loudly.
        console.error(`DepthScene: failed to load texture ${url}`, err);
        continueRender(handle);
      }
    );
  }, [url, handle]);
  return tex;
};

const Cutout: React.FC<{layer: Layer; idle: number; seed: number}> = ({layer, idle, seed}) => {
  const tex = useCutout(layer.src);
  const frame = useCurrentFrame();
  if (!tex) return null;
  // Deterministic yaw and pitch, never a plain bob (house rule). Different periods per
  // axis and a per-layer seed so a row of cutouts does not breathe in lockstep.
  const rotY = idle ? Math.sin(frame / 41 + seed) * idle : 0;
  const rotX = idle ? Math.sin(frame / 53 + seed * 1.7) * idle * 0.6 : 0;
  return (
    <mesh position={layer.pos} rotation={[rotX, rotY, 0]}>
      <planeGeometry args={[layer.w, layer.h]} />
      <meshBasicMaterial map={tex} transparent alphaTest={0.35} toneMapped={false} />
    </mesh>
  );
};

/**
 * Pure. Throws if `stops` is empty or `at` is not strictly ascending. Clamps t to
 * [0,1], finds the surrounding pair, lerps pos and look with an ease-in-out on
 * local segment progress. `look` defaults to the origin when a stop omits it.
 */
export const resolveStops = (stops: CameraStop[], t: number): {pos: Vec3; look: Vec3} => {
  if (stops.length === 0) {
    throw new Error('DepthScene: camera.stops is empty.');
  }
  for (let i = 1; i < stops.length; i++) {
    if (stops[i].at <= stops[i - 1].at) {
      throw new Error('DepthScene: camera.stops must be sorted ascending by `at`.');
    }
  }
  const clamped = Math.max(0, Math.min(1, t));
  const at = (s: CameraStop): {pos: Vec3; look: Vec3} => ({pos: s.pos, look: s.look ?? [0, 0, 0]});
  if (stops.length === 1 || clamped <= stops[0].at) return at(stops[0]);
  if (clamped >= stops[stops.length - 1].at) return at(stops[stops.length - 1]);

  let lo = stops[0];
  let hi = stops[stops.length - 1];
  for (let i = 0; i < stops.length - 1; i++) {
    if (clamped >= stops[i].at && clamped <= stops[i + 1].at) {
      lo = stops[i];
      hi = stops[i + 1];
      break;
    }
  }
  const segT = interpolate(clamped, [lo.at, hi.at], [0, 1], {
    easing: Easing.inOut(Easing.cubic),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const lerp = (a: number, b: number) => a + (b - a) * segT;
  const loLook = lo.look ?? [0, 0, 0];
  const hiLook = hi.look ?? [0, 0, 0];
  return {
    pos: [lerp(lo.pos[0], hi.pos[0]), lerp(lo.pos[1], hi.pos[1]), lerp(lo.pos[2], hi.pos[2])],
    look: [lerp(loLook[0], hiLook[0]), lerp(loLook[1], hiLook[1]), lerp(loLook[2], hiLook[2])],
  };
};

const CameraRig: React.FC<{from: number; to: number; stops: CameraStop[]}> = ({from, to, stops}) => {
  const frame = useCurrentFrame();
  const {camera} = useThree();
  const t = (frame - from) / Math.max(1, to - from);
  const {pos, look} = resolveStops(stops, t);
  camera.position.set(pos[0], pos[1], pos[2]);
  camera.lookAt(look[0], look[1], look[2]);
  camera.updateProjectionMatrix();
  return null;
};

export const DepthScene: React.FC<FullscreenSceneProps> = ({from, to, props}) => {
  const p = props as DepthProps;
  if (!p.layers || p.layers.length === 0) {
    throw new Error('DepthScene: `layers` is required and must be a non-empty array.');
  }
  if (!p.camera || !p.camera.stops || p.camera.stops.length === 0) {
    throw new Error('DepthScene: `camera.stops` is required and must be a non-empty array.');
  }
  const {width, height} = useVideoConfig();
  const bg = p.bg ?? '#08080a';
  const fov = p.camera.fov ?? 40;
  const idle = p.idle ?? 0.03;
  const firstPos = p.camera.stops[0].pos;
  const frame = useCurrentFrame();
  const bd = p.backdrop;
  const t = (frame - from) / Math.max(1, to - from);
  const driftScale = 1 + (bd?.drift ?? 0) * Math.min(1, Math.max(0, t));
  const grain = bd?.grain ?? 0;
  return (
    <AbsoluteFill style={{backgroundColor: bg}}>
      {bd?.image ? (
        <AbsoluteFill
          style={{
            backgroundImage: `url(${staticFile(bd.image)})`,
            backgroundSize: 'cover',
            backgroundPosition: 'center',
            transform: `scale(${driftScale})`,
            transformOrigin: '50% 40%',
          }}
        />
      ) : null}
      {bd?.particles ? <ParticleField {...bd.particles} /> : null}
      <ThreeCanvas linear width={width} height={height} camera={{fov, position: firstPos}}>
        <ambientLight intensity={1.4} />
        <CameraRig from={from} to={to} stops={p.camera.stops} />
        {bd?.image ? null : (
          <mesh position={[0, 0, -14]}>
            <planeGeometry args={[60, 90]} />
            <meshBasicMaterial color={bg} toneMapped={false} />
          </mesh>
        )}
        {p.layers.map((layer, i) => (
          <Cutout key={`${layer.src}-${i}`} layer={layer} idle={idle} seed={i * 1.31} />
        ))}
      </ThreeCanvas>
      {grain > 0 ? (
        <AbsoluteFill
          style={{
            opacity: grain,
            mixBlendMode: 'overlay',
            pointerEvents: 'none',
            backgroundImage: `url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 240 240'><filter id='g'><feTurbulence type='fractalNoise' baseFrequency='2.2' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%25' height='100%25' filter='url(%23g)'/></svg>")`,
            backgroundSize: '240px 240px',
          }}
        />
      ) : null}
    </AbsoluteFill>
  );
};
