/** Shared helpers, entity ids, labels and styling for the Sherpa cards. */
import { css, html, type TemplateResult, unsafeCSS } from 'lit';
import * as t from './tokens';

/** Lit's `css` tag only interpolates CSSResult; these are our own constants. */
export const cssVal = (value: string) => unsafeCSS(value);

export interface HassEntity {
  entity_id: string;
  state: string;
  attributes: Record<string, unknown>;
}

export interface Hass {
  states: Record<string, HassEntity>;
  language?: string;
  locale?: { language?: string };
  callService: (
    domain: string,
    service: string,
    data?: Record<string, unknown>,
  ) => Promise<unknown>;
}

/** Usable state of an entity, or undefined when it is missing, unknown or unavailable. */
export function str(hass: Hass | undefined, entityId?: string): string | undefined {
  const entity = entityId ? hass?.states[entityId] : undefined;
  if (!entity || entity.state === 'unavailable' || entity.state === 'unknown') return undefined;
  return entity.state;
}

export function num(hass: Hass | undefined, entityId?: string): number | undefined {
  const raw = str(hass, entityId);
  if (raw === undefined) return undefined;
  const value = Number(raw);
  return Number.isFinite(value) ? value : undefined;
}

export function isOn(hass: Hass | undefined, entityId?: string): boolean {
  return str(hass, entityId) === 'on';
}

export function attr<T = unknown>(
  hass: Hass | undefined, entityId: string, name: string,
): T | undefined {
  return hass?.states[entityId]?.attributes?.[name] as T | undefined;
}

/** A number for display, or an em dash. */
export function fmt(value: number | undefined | null, digits = 1): string {
  return value === undefined || value === null || !Number.isFinite(value)
    ? '—' : value.toFixed(digits);
}

/** The prefix the integration uses unless the entry was set up with another. */
export const DEFAULT_PREFIX = 'sherpa';

/**
 * Every entity id a card reads, from one prefix.
 *
 * One table, so a renamed entity is one edit -- and so the ids the cards bind
 * can be checked against the integration's entities.json in a test.
 */
export function ids(prefix = DEFAULT_PREFIX) {
  const s = (key: string) => `sensor.${prefix}_${key}`;
  const b = (key: string) => `binary_sensor.${prefix}_${key}`;
  return {
    climate: `climate.${prefix}_heat_pump`,
    waterIn: s('water_in'),
    waterOut: s('water_out'),
    dhwTank: s('dhw_tank'),
    outdoor: s('outdoor_air'),
    mode: s('mode'),
    waterTarget: s('water_target'),
    errorCode: s('error_code'),
    overrideCode: s('override_code'),
    pumpDuty: s('pump_duty'),
    heatingSetpoint: s('heating_setpoint'),
    coolingSetpoint: s('cooling_setpoint'),
    dhwSetpoint: s('dhw_setpoint'),
    compressor: b('compressor_running'),
    defrost: b('defrost'),
    pump: b('out_pump'),
    eh1: b('out_eh1'),
    eh2: b('out_eh2'),
    k5: b('out_k5'),
    boiler: b('out_boiler'),
    night: b('mode_night'),
    error: b('error'),
    warning: b('warning'),
    heatingCurve: b('heating_curve_enabled'),
    coolingCurve: b('cooling_curve_enabled'),
    /** Writable twins: present only with writes allowed and the check passed. */
    number: (key: string) => `number.${prefix}_${key}`,
    switch: (key: string) => `switch.${prefix}_${key}`,
  };
}

export type Ids = ReturnType<typeof ids>;

/**
 * Every visible string, in the two languages the product ships in.
 *
 * Picked by the dashboard user's language; anything else gets English. A
 * dashboard can still override single strings through the card's `labels`.
 */
const EN = {
  title: 'Heat pump',
  outdoorUnit: 'Outdoor unit',
  indoorUnit: 'Indoor unit',
  circuit: 'Heating circuit',
  coolingCircuit: 'Cooling circuit',
  tank: 'Hot water',
  compressor: 'Compressor',
  pump: 'Pump',
  defrost: 'Defrost',
  night: 'Night',
  target: 'target',
  calculated: 'calculated from the curve',
  fixed: 'fixed setpoint',
  supply: 'Supply',
  return: 'Return',
  outdoor: 'Outdoor',
  set: 'set',
  off: 'Off',
  heat: 'Heating',
  cool: 'Cooling',
  standby: 'Standby',
  heating: 'Heating',
  cooling: 'Cooling',
  domestic_hot_water: 'Hot water',
  anti_legionella: 'Anti-legionella',
  idle: 'Idle',
  running: 'Running',
  defrosting: 'Defrosting',
  modeOnPanel: 'The mode is set on the unit\'s panel.',
  heatingCurve: 'Heating curve',
  coolingCurve: 'Cooling curve',
  curveOff: 'curve off',
  setpoints: 'Setpoints',
  heatingSetpoint: 'Heating',
  coolingSetpoint: 'Cooling',
  dhwSetpoint: 'Hot water',
  readOnly: 'Read-only: writes are off, or this setpoint has not passed its write check.',
  noUnit: 'No Sherpa entities found for prefix',
  on: 'on',
} as const;

export type LabelKey = keyof typeof EN;

const UK: Record<LabelKey, string> = {
  title: 'Тепловий насос',
  outdoorUnit: 'Зовнішній блок',
  indoorUnit: 'Внутрішній блок',
  circuit: 'Контур опалення',
  coolingCircuit: 'Контур охолодження',
  tank: 'Гаряча вода',
  compressor: 'Компресор',
  pump: 'Насос',
  defrost: 'Розморожування',
  night: 'Ніч',
  target: 'ціль',
  calculated: 'розраховано за кривою',
  fixed: 'фіксована уставка',
  supply: 'Подача',
  return: 'Зворотка',
  outdoor: 'Надворі',
  set: 'уставка',
  off: 'Вимкнено',
  heat: 'Опалення',
  cool: 'Охолодження',
  standby: 'Очікування',
  heating: 'Опалення',
  cooling: 'Охолодження',
  domestic_hot_water: 'Гаряча вода',
  anti_legionella: 'Антилегіонела',
  idle: 'Очікує',
  running: 'Працює',
  defrosting: 'Розморожування',
  modeOnPanel: 'Режим задається на панелі агрегату.',
  heatingCurve: 'Крива опалення',
  coolingCurve: 'Крива охолодження',
  curveOff: 'крива вимкнена',
  setpoints: 'Уставки',
  heatingSetpoint: 'Опалення',
  coolingSetpoint: 'Охолодження',
  dhwSetpoint: 'Гаряча вода',
  readOnly: 'Лише читання: запис вимкнено або ця уставка не пройшла перевірку запису.',
  noUnit: 'Не знайдено сутностей Sherpa з префіксом',
  on: 'увімк.',
};

export function labels(
  hass: Hass | undefined,
  overrides?: Partial<Record<LabelKey, string>>,
): Record<LabelKey, string> {
  const language = (hass?.locale?.language || hass?.language || 'en').toLowerCase();
  const base = language.startsWith('uk') ? UK : EN;
  return { ...base, ...(overrides || {}) };
}

/** The line a curve draws: straight between its two points, held beyond them. */
export interface Curve {
  enabled?: boolean | null;
  outdoor_at_max_water?: number | null;
  max_water?: number | null;
  outdoor_at_min_water?: number | null;
  min_water?: number | null;
}

export function curvePoints(curve: Curve | undefined): [[number, number], [number, number]] | undefined {
  const values = [curve?.outdoor_at_max_water, curve?.max_water,
    curve?.outdoor_at_min_water, curve?.min_water];
  if (values.some((v) => v === undefined || v === null)) return undefined;
  const [x1, y1, x2, y2] = values as number[];
  if (x1 === x2) return undefined;
  return x1 < x2 ? [[x1, y1], [x2, y2]] : [[x2, y2], [x1, y1]];
}

export function curveAt(curve: Curve | undefined, outdoor: number): number | undefined {
  const points = curvePoints(curve);
  if (!points) return undefined;
  const [[x1, y1], [x2, y2]] = points;
  if (outdoor <= x1) return y1;
  if (outdoor >= x2) return y2;
  return y1 + ((outdoor - x1) * (y2 - y1)) / (x2 - x1);
}

export function errorRow(message: string): TemplateResult {
  return html`<div class="sherpa-error">${message}</div>`;
}

/**
 * Base styling: Home Assistant's theme variables first, the dark palette as the
 * fallback -- as the Futura cards do, so both follow one theme the same way.
 */
export const sharedStyles = css`
  :host {
    --sherpa-bg: var(--ha-card-background, var(--card-background-color, ${cssVal(t.GROUND)}));
    --sherpa-panel: var(--secondary-background-color, rgba(255, 255, 255, 0.06));
    --sherpa-text: var(--primary-text-color, ${cssVal(t.INK)});
    --sherpa-muted: var(--secondary-text-color, ${cssVal(t.DIM)});
    --sherpa-accent: var(--state-icon-active-color, ${cssVal(t.RUNNING)});
    --sherpa-running: ${cssVal(t.RUNNING)};
    --sherpa-warn: ${cssVal(t.WARN)};
    --sherpa-fault: ${cssVal(t.FAULT)};
    --sherpa-neutral: ${cssVal(t.NO_DATA)};
    --sherpa-radius: ${cssVal(t.RADIUS.canvas)};
    display: block;
  }

  ha-card {
    background: var(--sherpa-bg);
    color: var(--sherpa-text);
    border-radius: var(--sherpa-radius);
    padding: 16px;
    overflow: hidden;
  }

  .sherpa-error {
    padding: 12px;
    border-radius: 10px;
    background: color-mix(in srgb, var(--sherpa-fault) 15%, transparent);
    color: var(--sherpa-fault);
    font-size: 0.9rem;
  }

  .muted {
    color: var(--sherpa-muted);
  }

  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 10px;
  }

  .title {
    font-size: 1.05rem;
    font-weight: 500;
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    justify-content: flex-end;
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 9px;
    border-radius: ${cssVal(t.RADIUS.chip)};
    font-size: 0.78rem;
    background: var(--sherpa-panel);
    color: var(--sherpa-text);
    white-space: nowrap;
  }

  .chip ha-icon {
    --mdc-icon-size: 15px;
  }

  .chip.running {
    background: var(--sherpa-running);
    color: ${cssVal(t.ACCENT_INK)};
  }

  .chip.warn {
    background: color-mix(in srgb, var(--sherpa-warn) 30%, transparent);
  }

  .chip.fault {
    background: color-mix(in srgb, var(--sherpa-fault) 25%, transparent);
    color: var(--sherpa-fault);
  }

  /* The one "value over artwork" pill, shared with the Futura cards. */
  .readout-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border-radius: ${cssVal(t.RADIUS.pill)};
    background: rgba(12, 14, 18, 0.78);
    border: 1px solid rgba(255, 255, 255, 0.2);
    padding: 4px 8px;
    font-size: ${cssVal(t.PILL_FONT_SIZE)};
    font-weight: ${cssVal(t.PILL_FONT_WEIGHT)};
    color: rgba(255, 255, 255, 0.92);
    font-variant-numeric: tabular-nums;
  }

  @media (prefers-reduced-motion: reduce) {
    * {
      animation: none !important;
      transition: none !important;
    }
  }
`;
