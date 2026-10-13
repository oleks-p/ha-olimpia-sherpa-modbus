/**
 * The one place a colour, radius or stroke weight is decided.
 *
 * The surfaces, status colours, radii and type are the Futura cards' tokens,
 * unchanged, so the two product lines read as one family on a dashboard. What
 * is new is WATER: which circuit a pipe belongs to, the Sherpa's equivalent of
 * Futura's duct colours.
 *
 * Semantic groups are kept apart, as there:
 *
 *   SURFACE   what a thing is drawn on
 *   STATUS    what a reading or a machine is doing right now
 *   WATER     which circuit a pipe belongs to -- an identity, not a state
 *   GREY      decoration: idle pipes, outlines, furniture
 */

/* ── surfaces ────────────────────────────────────────────────────────────── */

/** The ground every schematic is drawn on. */
export const GROUND = '#0f1216';
/** A panel floating on the ground: a readout group, the chart. */
export const PANEL = '#1b1b1e';
/** Equipment bodies in the schematic, one step up from a panel. */
export const BODY = '#26262a';
/** Hairline between surfaces. */
export const BORDER = '#35353a';
/** Primary and secondary text on a surface. */
export const INK = '#f2f2f7';
export const DIM = '#8e8e93';

/* ── status ──────────────────────────────────────────────────────────────── */

/** A reading inside its comfortable band. */
export const OK = '#6fce6f';
/** A reading drifting out of band; an override (not a fault). */
export const WARN = '#b9b02f';
/** A reading out of band. */
export const BAD = '#d9564f';
/**
 * Equipment that is running: the compressor, the pump, a heater.
 *
 * Distinct from OK on purpose: "the compressor runs" and "the water is at its
 * target" are different facts.
 */
export const RUNNING = '#6edc96';
/** No telemetry for this thing. Grey, never red: an absent reading is not a fault. */
export const NO_DATA = '#79828f';
/** A real fault. The only red in the palette. */
export const FAULT = '#e0392c';
/** Text and glyphs printed on top of RUNNING, which is a light green. */
export const ACCENT_INK = '#0b2413';

/* ── water circuits ──────────────────────────────────────────────────────── */

/**
 * Which water a pipe carries.
 *
 * Supply and return of one circuit are one hue at two strengths, so a loop
 * reads as a loop. The DHW tank's charge is its own hue: it is the same water
 * as the heating circuit, but a different destination, and that is what the
 * picture has to show at a glance.
 */
export const WATER = {
  heatSupply: '#ff8a3d',
  heatReturn: '#c98a5f',
  coolSupply: '#19afff',
  coolReturn: '#5f9fc4',
  dhw: '#ff5d73',
  dhwReturn: '#c46a78',
} as const;

/* ── decoration ──────────────────────────────────────────────────────────── */

/** Greys for idle pipes, outlines and furniture that carry no state. */
export const GREY = {
  bright: '#e6e6ea',
  light: '#d7d7db',
  mid: '#c9c9ce',
  dim: '#8f8f95',
  dark: '#6a6a6f',
  darker: '#5d5d61',
  track: '#3a3a40',
} as const;

/* ── shape ───────────────────────────────────────────────────────────────── */

export const RADIUS = {
  /** A full-bleed drawing surface. */
  canvas: '18px',
  /** A small value readout sitting over artwork. */
  pill: '13px',
  /** Anything you press that is not a toggle chip. */
  button: '12px',
  /** A chip in a row of chips. */
  chip: '999px',
} as const;

/* ── stroke ladder ───────────────────────────────────────────────────────── */

/**
 * The schematic draws into a 900-wide viewBox rendered at about 500 px, so
 * these are viewBox units chosen to land near the Futura cards' rendered
 * weights: a pipe at about 3 px, an outline at 1.4 px.
 */
export const VIEWBOX_W = 900;
export const RENDER_W = 500;
const SCALE = VIEWBOX_W / RENDER_W;
/** A carried medium: water. Heavier than the outline -- what flows reads above what contains it. */
export const PIPE_W = Math.round(3 * SCALE * 10) / 10;
/** Equipment outline. */
export const OUTLINE_W = Math.round(1.4 * SCALE * 10) / 10;
/** Detail inside equipment: glyphs, the tank coil. */
export const DETAIL_W = Math.round(OUTLINE_W * 0.9 * 10) / 10;

/* ── type ────────────────────────────────────────────────────────────────── */

/** Readout type, in px: anything that lines up with artwork must not follow rem. */
export const PILL_FONT_SIZE = '12px';
export const PILL_FONT_WEIGHT = '500';
export const PILL_ICON_SIZE = '13px';
