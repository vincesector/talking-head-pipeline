import React from 'react';
import {Composition} from 'remotion';
import {Edit} from './scenes/Edit';
import type {Cue} from './lib/CaptionLayer';
import type {Plan} from './lib/plan';
import type {Track} from './lib/track';

import planData from '../plan.json';
import trackData from '../public/track.json';
import captionData from '../public/captions.json';

/**
 * One composition for every aspect ratio: plan.json carries width/height and lib/layouts.ts picks
 * the geometry profile (16:9 or 9:16) from them. Never fork the engine per aspect.
 */
// via unknown: a JSON import widens tuples (defocus.scatter) to number[] and string unions to
// string, which will not narrow to the Plan types without it.
const props = {
  plan: planData as unknown as Plan,
  track: trackData as unknown as Track,
  captions: captionData as unknown as Cue[],
};

export const RemotionRoot: React.FC = () => (
  <Composition
    id="Edit"
    component={Edit}
    defaultProps={props}
    durationInFrames={props.plan.durationInFrames}
    fps={props.plan.fps}
    width={props.plan.width}
    height={props.plan.height}
  />
);
