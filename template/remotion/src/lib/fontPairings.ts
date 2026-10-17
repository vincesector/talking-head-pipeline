import {loadFont as loadInstrumentSerif} from '@remotion/google-fonts/InstrumentSerif';
import {loadFont as loadInter} from '@remotion/google-fonts/Inter';

const inter = loadInter('normal', {
  weights: ['400', '800', '900'],
  subsets: ['latin'],
});

const instrumentSerif = loadInstrumentSerif('italic', {
  weights: ['400'],
  subsets: ['latin'],
});

export type FontPairingId =
  | 'inter-instrument'
  | 'inter-apple-garamond'
  | 'helvetica-instrument'
  | 'druk-helvetica'
  | 'scholar-helvetica';

export type FontPairing = {
  baseFamily: string;
  baseWeight: number;
  emphasisFamily: string;
  emphasisWeight: number;
  emphasisStyle: 'normal' | 'italic';
  exactAssetsAvailable: boolean;
};

export const fontPairings: Record<FontPairingId, FontPairing> = {
  // Default: both faces from Google Fonts (OFL), so it renders identically on macOS and Linux.
  'inter-instrument': {
    baseFamily: inter.fontFamily,
    baseWeight: 800,
    emphasisFamily: instrumentSerif.fontFamily,
    emphasisWeight: 400,
    emphasisStyle: 'italic',
    exactAssetsAvailable: true,
  },
  'inter-apple-garamond': {
    baseFamily: inter.fontFamily,
    baseWeight: 900,
    emphasisFamily: '"Apple Garamond", "Cormorant Garamond", Georgia, serif',
    emphasisWeight: 300,
    emphasisStyle: 'italic',
    exactAssetsAvailable: false,
  },
  'helvetica-instrument': {
    baseFamily: '"Helvetica Neue", Helvetica, Arial, sans-serif',
    baseWeight: 700,
    emphasisFamily: instrumentSerif.fontFamily,
    emphasisWeight: 400,
    emphasisStyle: 'italic',
    exactAssetsAvailable: true,
  },
  'druk-helvetica': {
    baseFamily: '"Druk Wide", "Arial Black", Impact, sans-serif',
    baseWeight: 900,
    emphasisFamily: '"Helvetica Neue", Helvetica, Arial, sans-serif',
    emphasisWeight: 700,
    emphasisStyle: 'normal',
    exactAssetsAvailable: false,
  },
  'scholar-helvetica': {
    baseFamily: '"Scholar", "Iowan Old Style", Georgia, serif',
    baseWeight: 400,
    emphasisFamily: '"Helvetica Neue", Helvetica, Arial, sans-serif',
    emphasisWeight: 400,
    emphasisStyle: 'normal',
    exactAssetsAvailable: false,
  },
};
