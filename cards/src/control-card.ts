/**
 * The heat pump's status and settings: the mode as the panel has it, the water
 * against its target, the climatic curve with today's operating point, and the
 * setpoints.
 *
 * The mode is shown, not offered: over Modbus there is no command for it while
 * the panel is in control (docs/p5_mode_research.md). A setpoint gets a stepper
 * only where its number entity exists -- writes allowed on the entry, and the
 * write check passed on this unit. Everywhere else it is a reading with a lock,
 * never a control that would fail when pressed.
 *
 * Steps are collected for a moment before anything is sent: the integration
 * accepts one write per register every 10 s, so three quick taps sent one by one
 * would be two refusals.
 */
import {
  LitElement,
  type PropertyDeclarations,
  css,
  html,
  nothing,
  svg,
  type TemplateResult,
} from 'lit';
import {
  type Curve,
  type Hass,
  type Ids,
  type LabelKey,
  DEFAULT_PREFIX,
  attr,
  curveAt,
  curvePoints,
  cssVal,
  errorRow,
  fmt,
  ids,
  isOn,
  labels,
  num,
  sharedStyles,
  str,
} from './shared';
import * as t from './tokens';

export interface ControlCardConfig {
  type: string;
  prefix?: string;
  title?: string;
  show_curve?: boolean;
  show_setpoints?: boolean;
  labels?: Partial<Record<LabelKey, string>>;
}

/** How long taps are collected before the write goes out. */
const SETTLE_MS = 1500;

interface Setpoint {
  key: 'heating_setpoint' | 'cooling_setpoint' | 'dhw_setpoint';
  label: LabelKey;
  sensor: (id: Ids) => string;
}

const SETPOINTS: Setpoint[] = [
  { key: 'heating_setpoint', label: 'heatingSetpoint', sensor: (id) => id.heatingSetpoint },
  { key: 'cooling_setpoint', label: 'coolingSetpoint', sensor: (id) => id.coolingSetpoint },
  { key: 'dhw_setpoint', label: 'dhwSetpoint', sensor: (id) => id.dhwSetpoint },
];

const CHART = { w: 320, h: 150, left: 34, right: 10, top: 12, bottom: 24 };

export class SherpaControlCard extends LitElement {
  static override properties: PropertyDeclarations = {
    hass: { attribute: false },
    _config: { state: true },
    _draft: { state: true },
  };

  hass?: Hass;
  private _config?: ControlCardConfig;
  /** Values tapped to but not yet sent, by setpoint key. */
  private _draft: Record<string, number> = {};
  private _timers: Record<string, number> = {};

  setConfig(config: ControlCardConfig): void {
    if (!config) throw new Error('Invalid configuration');
    this._config = { prefix: DEFAULT_PREFIX, show_curve: true, show_setpoints: true, ...config };
  }

  static getStubConfig(): ControlCardConfig {
    return { type: 'custom:sherpa-control-card' };
  }

  getCardSize(): number {
    return 7;
  }

  getGridOptions() {
    return { columns: 6, rows: 7, min_columns: 4, min_rows: 4 };
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    Object.values(this._timers).forEach((timer) => window.clearTimeout(timer));
    this._timers = {};
  }

  private get _ids(): Ids {
    return ids(this._config?.prefix);
  }

  override render(): TemplateResult {
    const hass = this.hass;
    const id = this._ids;
    const l = labels(hass, this._config?.labels);
    if (!hass || !hass.states[id.climate]) {
      return html`<ha-card>${errorRow(`${l.noUnit} "${this._config?.prefix}".`)}</ha-card>`;
    }
    const selected = str(hass, id.climate) ?? 'off';
    const action = attr<string>(hass, id.climate, 'hvac_action');
    const dhw = attr<boolean>(hass, id.climate, 'dhw_in_progress');
    const target = num(hass, id.waterTarget);
    const source = attr<string>(hass, id.waterTarget, 'source');
    const modeLabel = selected === 'heat' ? l.heat : selected === 'cool' ? l.cool : l.off;
    // What the compressor is doing -- the mode chip already says which mode.
    const actionLabel = dhw ? l.domestic_hot_water
      : action === 'heating' || action === 'cooling' ? l.running
        : action === 'defrosting' ? l.defrosting
          : action === 'idle' ? l.idle : undefined;

    return html`
      <ha-card>
        <div class="head">
          <span class="title">${this._config?.title ?? l.title}</span>
          <span class="chips">
            <span class="chip" title=${l.modeOnPanel}>
              <ha-icon icon="mdi:lock-outline"></ha-icon>${modeLabel}
            </span>
            ${actionLabel && selected !== 'off'
              ? html`<span class="chip ${action === 'heating' || action === 'cooling' ? 'running' : action === 'defrosting' ? 'warn' : ''}">${actionLabel}</span>`
              : nothing}
            ${isOn(hass, id.night) ? html`<span class="chip"><ha-icon icon="mdi:weather-night"></ha-icon>${l.night}</span>` : nothing}
          </span>
        </div>

        <div class="water">
          <div>
            <div class="big">${fmt(num(hass, id.waterOut))}<span class="unit">°C</span></div>
            <div class="muted small">${l.supply}</div>
          </div>
          <div>
            <div class="mid">${fmt(target)}<span class="unit">°C</span></div>
            <div class="muted small" title=${source?.endsWith('_curve') ? l.calculated : l.fixed}>${l.target}${source?.endsWith('_curve') ? ' *' : ''}</div>
          </div>
          <div>
            <div class="mid">${fmt(num(hass, id.outdoor))}<span class="unit">°C</span></div>
            <div class="muted small">${l.outdoor}</div>
          </div>
        </div>

        ${this._config?.show_curve ? this._curve(selected === 'cool' ? 'cooling' : 'heating', l, selected !== 'off') : nothing}
        ${source?.endsWith('_curve') ? html`<div class="muted small foot">* ${l.calculated}</div>` : nothing}
        ${this._tank(l)}
        ${this._config?.show_setpoints ? this._setpoints(l) : nothing}
      </ha-card>
    `;
  }

  private _curve(kind: 'heating' | 'cooling', l: Record<LabelKey, string>, active: boolean): TemplateResult {
    const hass = this.hass;
    const id = this._ids;
    const curve = attr<Curve>(hass, id.climate, `${kind}_curve`);
    const points = curvePoints(curve);
    const outdoor = num(hass, id.outdoor);
    const fixed = num(hass, kind === 'heating' ? id.heatingSetpoint : id.coolingSetpoint);
    const enabled = curve?.enabled !== false;
    if (!points) return html``;
    const [[x1, y1], [x2, y2]] = points;
    const xs = [x1, x2, ...(outdoor === undefined ? [] : [outdoor])];
    const xMin = Math.min(...xs) - 5;
    const xMax = Math.max(...xs) + 5;
    const ys = [y1, y2, ...(fixed === undefined ? [] : [fixed])];
    const yMin = Math.floor(Math.min(...ys) - 3);
    const yMax = Math.ceil(Math.max(...ys) + 3);
    const px = (x: number) => CHART.left + ((x - xMin) / (xMax - xMin)) * (CHART.w - CHART.left - CHART.right);
    const py = (y: number) => CHART.top + ((yMax - y) / (yMax - yMin)) * (CHART.h - CHART.top - CHART.bottom);
    const colour = kind === 'heating' ? t.WATER.heatSupply : t.WATER.coolSupply;
    const line = `M ${px(xMin)} ${py(y1)} L ${px(x1)} ${py(y1)} L ${px(x2)} ${py(y2)} L ${px(xMax)} ${py(y2)}`;
    const here = outdoor === undefined ? undefined : enabled ? curveAt(curve, outdoor) : fixed;
    const xTicks = [x1, x2, ...(outdoor === undefined ? [] : [Math.round(outdoor)])];
    const yTicks = [y1, y2];

    return html`
      <div class="section">
        <div class="row">
          <span>${kind === 'heating' ? l.heatingCurve : l.coolingCurve}</span>
          ${enabled ? nothing : html`<span class="chip">${l.curveOff}</span>`}
        </div>
        <svg class="chart" viewBox="0 0 ${CHART.w} ${CHART.h}" role="img"
             aria-label=${kind === 'heating' ? l.heatingCurve : l.coolingCurve}>
          <rect class="plot" x=${CHART.left} y=${CHART.top} width=${CHART.w - CHART.left - CHART.right}
                height=${CHART.h - CHART.top - CHART.bottom} rx="6" />
          ${yTicks.map((y) => svg`
            <line class="grid" x1=${CHART.left} x2=${CHART.w - CHART.right} y1=${py(y)} y2=${py(y)} />
            <text x=${CHART.left - 6} y=${py(y) + 4} text-anchor="end" class="tick">${fmt(y, 0)}°</text>`)}
          ${xTicks.map((x) => svg`
            <text x=${px(x)} y=${CHART.h - 8} text-anchor="middle" class="tick">${fmt(x, 0)}°</text>`)}
          <path d=${line} fill="none" stroke=${colour} stroke-width="2.4"
                stroke-opacity=${enabled ? 1 : 0.35} stroke-linejoin="round" />
          ${!enabled && fixed !== undefined ? svg`
            <line x1=${CHART.left} x2=${CHART.w - CHART.right} y1=${py(fixed)} y2=${py(fixed)}
                  stroke=${colour} stroke-width="2" stroke-dasharray="5 4" />` : nothing}
          ${outdoor !== undefined && here !== undefined ? svg`
            <line class="now" x1=${px(outdoor)} x2=${px(outdoor)} y1=${CHART.top}
                  y2=${CHART.h - CHART.bottom} />
            <circle class=${active ? 'point' : 'point hollow'} cx=${px(outdoor)} cy=${py(here)} r="5"
                    style="--point:${colour}" />` : nothing}
        </svg>
      </div>
    `;
  }

  private _tank(l: Record<LabelKey, string>): TemplateResult {
    const hass = this.hass;
    const id = this._ids;
    const tank = num(hass, id.dhwTank);
    const set = num(hass, id.dhwSetpoint);
    const share = tank === undefined || set === undefined || set <= 0
      ? 0 : Math.max(0, Math.min(1, tank / set));
    return html`
      <div class="section">
        <div class="row">
          <span>${l.tank}</span>
          <span class="value">${fmt(tank)} / ${fmt(set)} °C</span>
        </div>
        <div class="bar"><span style="width:${(share * 100).toFixed(0)}%"></span></div>
      </div>
    `;
  }

  private _setpoints(l: Record<LabelKey, string>): TemplateResult {
    const hass = this.hass;
    const id = this._ids;
    let locked = false;
    const rows = SETPOINTS.map((sp) => {
      const entity = id.number(sp.key);
      const writable = hass?.states[entity] !== undefined && str(hass, entity) !== undefined;
      locked ||= !writable;
      const value = this._draft[sp.key] ?? (writable ? num(hass, entity) : num(hass, sp.sensor(id)));
      return html`
        <div class="row setpoint">
          <span>${l[sp.label]}</span>
          ${writable ? html`
            <span class="stepper">
              <button @click=${() => this._step(sp.key, entity, -1)} aria-label="−">−</button>
              <span class="value ${this._draft[sp.key] !== undefined ? 'pending' : ''}">${fmt(value)} °C</span>
              <button @click=${() => this._step(sp.key, entity, 1)} aria-label="+">+</button>
            </span>` : html`
            <span class="value" title=${l.readOnly}>
              ${fmt(value)} °C <ha-icon class="lock" icon="mdi:lock-outline"></ha-icon>
            </span>`}
        </div>
      `;
    });
    return html`
      <div class="section">
        <div class="row"><span class="muted">${l.setpoints}</span></div>
        ${rows}
        ${locked ? html`<div class="muted small">${l.readOnly}</div>` : nothing}
      </div>
    `;
  }

  private _step(key: string, entity: string, direction: 1 | -1): void {
    const state = this.hass?.states[entity];
    if (!state) return;
    const step = Number(state.attributes.step ?? 0.5);
    const min = Number(state.attributes.min ?? -Infinity);
    const max = Number(state.attributes.max ?? Infinity);
    const from = this._draft[key] ?? Number(state.state);
    if (!Number.isFinite(from)) return;
    const next = Math.round(Math.min(max, Math.max(min, from + direction * step)) / step) * step;
    this._draft = { ...this._draft, [key]: Number(next.toFixed(3)) };
    window.clearTimeout(this._timers[key]);
    this._timers[key] = window.setTimeout(() => this._send(key, entity), SETTLE_MS);
  }

  private async _send(key: string, entity: string): Promise<void> {
    const value = this._draft[key];
    delete this._timers[key];
    try {
      if (value !== undefined && value !== Number(this.hass?.states[entity]?.state)) {
        await this.hass?.callService('number', 'set_value', { entity_id: entity, value });
      }
    } catch {
      // Home Assistant has already shown the reason (out of range, rate limit,
      // not applied); the entity keeps showing what the unit really holds.
    } finally {
      const { [key]: _sent, ...rest } = this._draft;
      this._draft = rest;
    }
  }

  static override styles = [
    sharedStyles,
    css`
      .water {
        display: grid;
        grid-template-columns: 1.3fr 1fr 1fr;
        align-items: end;
        gap: 8px;
        margin-bottom: 12px;
        font-variant-numeric: tabular-nums;
      }

      .big {
        font-size: 2.1rem;
        font-weight: 400;
        line-height: 1.1;
      }

      .mid {
        font-size: 1.25rem;
        line-height: 1.2;
      }

      .unit {
        font-size: 0.55em;
        margin-left: 2px;
        color: var(--sherpa-muted);
      }

      .small {
        font-size: 0.75rem;
      }

      .foot {
        margin-top: 2px;
      }

      .section {
        margin-top: 10px;
      }

      .row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        font-size: 0.9rem;
      }

      .setpoint {
        padding: 5px 0;
        border-top: 1px solid var(--divider-color, ${cssVal(t.BORDER)});
      }

      .value {
        font-variant-numeric: tabular-nums;
        display: inline-flex;
        align-items: center;
        gap: 4px;
      }

      .value.pending {
        color: var(--sherpa-accent);
      }

      .lock {
        --mdc-icon-size: 15px;
        color: var(--sherpa-muted);
      }

      .stepper {
        display: inline-flex;
        align-items: center;
        gap: 8px;
      }

      .stepper button {
        width: 30px;
        height: 30px;
        border-radius: ${cssVal(t.RADIUS.button)};
        border: none;
        background: var(--sherpa-panel);
        color: var(--sherpa-text);
        font-size: 1.1rem;
        cursor: pointer;
      }

      .stepper button:hover {
        background: color-mix(in srgb, var(--sherpa-accent) 25%, var(--sherpa-panel));
      }

      .chart {
        display: block;
        width: 100%;
        height: auto;
        margin-top: 6px;
      }

      .tick {
        font-size: 10px;
        fill: var(--sherpa-muted);
      }

      /* The chart follows the theme: no fixed dark block on a light card. */
      .plot {
        fill: var(--sherpa-panel);
      }

      .grid {
        stroke: var(--divider-color, ${cssVal(t.BORDER)});
        stroke-width: 1;
      }

      .now {
        stroke: var(--sherpa-muted);
        stroke-width: 1;
        stroke-dasharray: 3 3;
        opacity: 0.7;
      }

      .point {
        fill: var(--point);
        stroke: var(--sherpa-bg);
        stroke-width: 2;
      }

      .point.hollow {
        fill: var(--sherpa-bg);
        stroke: var(--point);
      }

      .bar {
        height: 6px;
        border-radius: 3px;
        background: var(--sherpa-panel);
        margin-top: 6px;
        overflow: hidden;
      }

      .bar span {
        display: block;
        height: 100%;
        background: ${cssVal(t.WATER.dhw)};
        border-radius: 3px;
      }
    `,
  ];
}
