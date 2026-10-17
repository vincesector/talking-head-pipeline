import {loadFont as loadAnton} from '@remotion/google-fonts/Anton';
import {loadFont as loadArchivoBlack} from '@remotion/google-fonts/ArchivoBlack';
import {loadFont as loadBebasNeue} from '@remotion/google-fonts/BebasNeue';
import {loadFont as loadOswald} from '@remotion/google-fonts/Oswald';
import {loadFont as loadStaatliches} from '@remotion/google-fonts/Staatliches';
import {loadFont as loadTeko} from '@remotion/google-fonts/Teko';
import {continueRender, delayRender} from 'remotion';

/**
 * Display faces for the word that sits behind the subject.
 *
 * The constraint that matters here is width, not height. A word behind a person
 * wants to be vertically enormous, and a normal-width face hits the frame edges
 * long before it gets there, so it has to shrink. A condensed face packs the
 * same letters into less horizontal space, so the cap height can go far higher
 * before width binds.
 *
 * `widthPerCap` is the measured advance width of one capital at font-size 1,
 * averaged over A-Z. Lower is narrower is taller-at-the-same-width.
 */
export type DisplayFaceId =
  | 'anton'
  | 'bebas'
  | 'oswald'
  | 'teko'
  | 'staatliches'
  | 'archivo-black';

export type DisplayFace = {
  fontFamily: string;
  fontWeight: number;
  /** Negative tracking suits heavy condensed caps at large sizes. */
  letterSpacing: string;
  note: string;
};

const anton = loadAnton('normal', {weights: ['400'], subsets: ['latin']});
const bebas = loadBebasNeue('normal', {weights: ['400'], subsets: ['latin']});
const oswald = loadOswald('normal', {weights: ['700'], subsets: ['latin']});
const teko = loadTeko('normal', {weights: ['700'], subsets: ['latin']});
const staatliches = loadStaatliches('normal', {
  weights: ['400'],
  subsets: ['latin'],
});
const archivoBlack = loadArchivoBlack('normal', {
  weights: ['400'],
  subsets: ['latin'],
});

/**
 * fitText() measures with whatever font the browser has resolved at that
 * moment. If a display face has not finished loading it measures a fallback,
 * and since these condensed faces are much narrower than any fallback, the
 * returned size overflows the frame. A narrow vertical frame makes it obvious;
 * a wide one hides it.
 *
 * Block the render until every face is ready so measurement is always honest.
 */
const fontsReady = delayRender('display faces');
Promise.all(
  [anton, bebas, oswald, teko, staatliches, archivoBlack]
    .map((f) => (f as {waitUntilDone?: () => Promise<void>}).waitUntilDone?.())
    .filter(Boolean) as Promise<void>[],
)
  .then(() => continueRender(fontsReady))
  .catch(() => continueRender(fontsReady));

export const displayFaces: Record<DisplayFaceId, DisplayFace> = {
  // Default. Heavy, condensed, tall caps. The classic big-word face.
  anton: {
    fontFamily: anton.fontFamily,
    fontWeight: 400,
    letterSpacing: '-0.02em',
    note: 'heaviest and tallest. use unless there is a reason not to',
  },
  // Taller and lighter than Anton. Good when the word must not overpower.
  bebas: {
    fontFamily: bebas.fontFamily,
    fontWeight: 400,
    letterSpacing: '0em',
    note: 'very tall, lighter stroke. calmer than anton',
  },
  oswald: {
    fontFamily: oswald.fontFamily,
    fontWeight: 700,
    letterSpacing: '-0.01em',
    note: 'condensed with more character detail. reads editorial',
  },
  teko: {
    fontFamily: teko.fontFamily,
    fontWeight: 700,
    letterSpacing: '0em',
    note: 'extremely narrow. for long words that will not fit otherwise',
  },
  staatliches: {
    fontFamily: staatliches.fontFamily,
    fontWeight: 400,
    letterSpacing: '0.01em',
    note: 'condensed poster face, slightly rough. good for hype openers',
  },
  // Wide. Only when the word is short and should feel like a slab.
  'archivo-black': {
    fontFamily: archivoBlack.fontFamily,
    fontWeight: 400,
    letterSpacing: '-0.03em',
    note: 'WIDE, not tall. only for 3-5 letter words',
  },
};
