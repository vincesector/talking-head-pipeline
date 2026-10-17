import React from 'react';
import {AbsoluteFill, Img, OffthreadVideo, staticFile} from 'remotion';
import {C, FONT} from '../lib/theme';

/**
 * Pages for the screen scene's browser window. The viewport is 1698 x 888 design px.
 *
 * - `image`: a full-page screenshot from public/ (props.src), top-aligned.
 * - `video`: a screen recording from public/ (props.src), muted, starting at props.startFrom.
 * - `example`: a placeholder page that shows where your content goes. Replace it.
 *
 * For anything the camera zooms into, rebuild the page in code (React + the site's own colours and
 * fonts, real data only): a screenshot goes soft at 2x and its text cannot move.
 * If you recreate a real product's UI, keep it one-to-one with the real thing (labels, layout,
 * flow) and only change the data, which must be real.
 */
export type PageProps = {props: Record<string, unknown>};

const ImagePage: React.FC<PageProps> = ({props}) => (
  <Img src={staticFile(props.src as string)} style={{width: '100%', display: 'block'}} />
);

const VideoPage: React.FC<PageProps> = ({props}) => (
  <AbsoluteFill>
    <OffthreadVideo src={staticFile(props.src as string)} startFrom={(props.startFrom as number) ?? 0} muted style={{width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top'}} />
  </AbsoluteFill>
);

const ExamplePage: React.FC<PageProps> = ({props}) => (
  <AbsoluteFill style={{background: C.bg, fontFamily: FONT, color: C.text, padding: 56, boxSizing: 'border-box'}}>
    <div style={{fontSize: 40, fontWeight: 800}}>{(props.heading as string) ?? 'Your page goes here'}</div>
    <div style={{fontSize: 22, color: C.muted, marginTop: 10}}>screen/pages.tsx: build the page as React, or use the image / video page.</div>
    <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 24, marginTop: 40}}>
      {['Card A', 'Card B', 'Card C'].map((t) => (
        <div key={t} style={{height: 220, borderRadius: 16, background: C.panel, border: `1.5px solid ${C.border}`, padding: 24, boxSizing: 'border-box', fontSize: 26, color: C.muted}}>
          {t}
        </div>
      ))}
    </div>
    <div style={{marginTop: 32, height: 280, borderRadius: 16, background: C.panel, border: `1.5px solid ${C.border}`}} />
  </AbsoluteFill>
);

export const PAGES: Record<string, React.FC<PageProps>> = {
  image: ImagePage,
  video: VideoPage,
  example: ExamplePage,
};
