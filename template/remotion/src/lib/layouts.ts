/**
 * Layout profiles.
 *
 * The engine is aspect-agnostic. Punch curves, head tracking, matting, the
 * world-space transform and the occlusion sandwich behave identically at any
 * frame size. What changes between 16:9 and 9:16 is roughly forty numbers:
 * where things anchor, how big they are, and which parts of frame are off
 * limits.
 *
 * So there is one pipeline and two profiles, not two pipelines. A fix lands
 * once.
 *
 * The horizontal values are the exact ones a shipped 16:9 edit used.
 * Do not "tidy" them; the render is signed off against these numbers.
 *
 * One trap worth stating: `size` is a fraction of frame HEIGHT everywhere in
 * this codebase. A circular badge at size s is therefore s * (height/width)
 * wide. On 16:9 that is s * 0.5625, on 9:16 it is s * 1.778. The same number
 * means a mark three times wider in vertical. Vertical sizes are smaller for
 * that reason alone, not because the marks should look smaller.
 */

export type LayoutId = 'horizontal' | 'vertical';

export type Layout = {
  /** Off-limits insets, normalized. Vertical reserves platform UI. */
  safe: {top: number; bottom: number; left: number; right: number};
  logo: {
    /** Where a side/anchored logo group centres. */
    x: number;
    y: number;
    /** Stack direction for a multi-logo group. */
    direction: 'column' | 'row';
    /** Default height fraction for one mark in the group. */
    size: number;
    gap: number;
  };
  caption: {
    /** Fixed-caption centre, normalized y. */
    y: number;
    /** Container width as a fraction of frame width. */
    width: number;
    /** Font size as a fraction of frame height. */
    size: number;
    /** Head-tracked caption clearance above the head. */
    trackedOffset: number;
  };
  bigWord: {
    /** Stack height fraction. */
    size: number;
    /** Width is the binding constraint; narrow frames need shorter lines. */
    maxLines: number;
    /** Fraction of frame width the word may occupy. */
    widthLimit: number;
    /**
     * Vertical bias as a fraction of frame height, negative is up.
     *
     * Centring the word is right on 16:9 and wrong on 9:16. Measured subject
     * coverage of the word's band: the approved horizontal look sits at 22.4%
     * occluded, which reads as "passing behind him". Vertical centred lands on
     * the torso, the widest part of the silhouette, at 52.6% occluded, where
     * the word is simply unreadable. Coverage by band in 9:16: head 27-35%,
     * torso 70-89%.
     *
     * -0.26 puts the vertical word's centre at y 0.24, which measures 23.1%
     * occluded and so matches the horizontal feel rather than guessing.
     */
    y: number;
  };
  scatter: {
    /** Sensible size range for badges behind the subject. */
    minSize: number;
    maxSize: number;
    /** Rough item count the frame carries before it reads as clutter. */
    items: number;
  };
  /**
   * Defocus for anything sandwiched between the subject and the background.
   *
   * Many creators shoot wide open: he is sharp, the room behind him is heavily out of
   * focus. A razor-sharp word sitting "between" those two planes is physically
   * impossible, and that is what makes a sandwiched graphic read as pasted on
   * rather than present in the room. A little blur puts it in the space.
   *
   * Values are fractions of frame height so they survive any resolution.
   * Enough to feel, never enough to hurt legibility.
   */
  depth: {
    /** Hero word. It is huge, so it tolerates more before it softens. */
    heroBlur: number;
    /** Scatter range, applied inversely to size: smaller reads as further. */
    scatterBlur: [number, number];
  };
  /** Offset reframes need lateral room. Vertical has none worth the zoom. */
  allowReframe: boolean;
};

export const layouts: Record<LayoutId, Layout> = {
  // Measured on one 16:9 shoot: face spans x 0.40-0.60, left third is the
  // quiet side at 19.6 mean luma, bottom band .86-.97 is calm at 46.
  horizontal: {
    safe: {top: 0.04, bottom: 0.04, left: 0.03, right: 0.03},
    logo: {x: 0.19, y: 0.5, direction: 'column', size: 0.26, gap: 34},
    caption: {y: 0.87, width: 0.78, size: 0.055, trackedOffset: 0.055},
    bigWord: {size: 0.82, maxLines: 2, widthLimit: 0.94, y: 0},
    scatter: {minSize: 0.22, maxSize: 0.30, items: 8},
    depth: {heroBlur: 0.0035, scatterBlur: [0.0015, 0.006]},
    allowReframe: true,
  },

  // Measured on the 2026-06-27 vertical take: face spans x 0.353-0.687, so the
  // side gaps are half the horizontal ones and not worth fighting for. The
  // usable space is vertical: 533px of clean dark frame above his head at luma
  // 15.7 with zero bright pixels. Logos go there, in a row.
  vertical: {
    // bottom 15% is where TikTok and Reels draw their own UI, right 12% is the
    // action rail. Nothing important may live there.
    safe: {top: 0.06, bottom: 0.15, left: 0.04, right: 0.12},
    logo: {x: 0.5, y: 0.13, direction: 'row', size: 0.115, gap: 44},
    // 0.79 sits in the calm band (.74-.84, luma 27) and clears the UI zone.
    caption: {y: 0.79, width: 0.88, size: 0.032, trackedOffset: 0.045},
    // A narrow frame binds the hero word by width long before height, so the
    // stack ends up smaller no matter what size says. Prefer short words and
    // more lines here.
    // 0.92 technically fits, but in a narrow frame text running to 96% of the
    // width READS as clipped even when it is not. Measured: at 0.92 the word
    // spanned x 0.053-0.959 and looked cut. 0.84 gives visible air.
    bigWord: {size: 0.55, maxLines: 4, widthLimit: 0.84, y: -0.26},
    scatter: {minSize: 0.09, maxSize: 0.14, items: 6},
    depth: {heroBlur: 0.003, scatterBlur: [0.0012, 0.005]},
    allowReframe: false,
  },
};

export const layoutFor = (width: number, height: number): LayoutId =>
  height > width ? 'vertical' : 'horizontal';

export const resolveLayout = (
  width: number,
  height: number,
  override?: LayoutId,
): Layout => layouts[override ?? layoutFor(width, height)];
