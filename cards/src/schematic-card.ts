/**
 * The plant as a schematic: outdoor unit, indoor unit, the three-way valve, the
 * heating (or cooling) circuit and the hot-water tank, with the water route the
 * unit is using right now.
 *
 * Which branch is live follows the unit's mode, not the valve's output bit:
 * ADDR259 can invert the valve's polarity, so "energised" means the tank on one
 * installation and the circuit on another, while "making hot water" means the
 * tank everywhere. The pipes animate only while the circulation pump runs.
 *
 * It draws only what the unit reports. The water target is the integration's
 * calculation from the climatic curve and is labelled as such; there is no flow
 * rate or power here because the Sherpa does not publish them.
 */
import { LitElement, type PropertyDeclarations, css, html, nothing, svg, type TemplateResult } from 'lit';
import {
  type Hass,
  type Ids,
  type LabelKey,
  DEFAULT_PREFIX,
  attr,
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

export interface SchematicCardConfig {
  type: string;
  prefix?: string;
  title?: string;
  labels?: Partial<Record<LabelKey, string>>;
}

const W = 900;
const H = 440;

/** Equipment, in viewBox units. */
const ODU = { x: 20, y: 110, w: 190, h: 230 };
const IDU = { x: 280, y: 110, w: 190, h: 230 };
const CIRCUIT = { x: 690, y: 115, w: 200, h: 110 };
const TANK = { x: 690, y: 245, w: 200, h: 185 };
const VALVE = { x: 556, y: 170 };
const FAN = { x: ODU.x + ODU.w / 2, y: ODU.y + 112, r: 56 };
const PUMP = { x: IDU.x + IDU.w / 2, y: IDU.y + 185, r: 20 };
/** The two electric heaters, side by side above the pump. */
const HEATERS = [IDU.x + IDU.w / 2 - 38, IDU.x + IDU.w / 2 + 38].map((x) => ({ x, y: IDU.y + 108 }));
/** The tank coil's two passes. */
const COIL_IN = 366;
const COIL_OUT = 410;

/**
 * The pipes. The heating return runs over the top and the tank return
 * underneath, so no two pipes cross and nothing needs a bridge.
 */
const PIPES = {
  supply: `M ${IDU.x + IDU.w} ${VALVE.y} H ${VALVE.x - 16}`,
  toCircuit: `M ${VALVE.x + 16} ${VALVE.y} H ${CIRCUIT.x}`,
  circuitReturn: `M ${CIRCUIT.x + CIRCUIT.w / 2} ${CIRCUIT.y} V 60 H ${IDU.x + 140} V ${IDU.y}`,
  toTank: `M ${VALVE.x} ${VALVE.y + 16} V ${COIL_IN} H ${TANK.x + 14}`,
  tankReturn: `M ${TANK.x + 14} ${COIL_OUT} H ${IDU.x + 50} V ${IDU.y + IDU.h}`,
} as const;

/** The heat exchanger coil inside the tank: two passes, in and back. */
const COIL = (() => {
  const left = TANK.x + 14;
  const right = TANK.x + TANK.w - 26;
  const waves = 5;
  const step = (right - left) / waves;
  let d = `M ${left} ${COIL_IN}`;
  for (let i = 0; i < waves; i += 1) {
    d += ` q ${step / 4} -14 ${step / 2} 0 t ${step / 2} 0`;
  }
  d += ` C ${right + 22} ${COIL_IN} ${right + 22} ${COIL_OUT} ${right} ${COIL_OUT}`;
  for (let i = 0; i < waves; i += 1) {
    d += ` q ${-step / 4} 14 ${-step / 2} 0 t ${-step / 2} 0`;
  }
  return d;
})();

type Route = 'circuit' | 'tank' | 'none';
type Circuit = 'heat' | 'cool';

/** Position an HTML overlay at viewBox coordinates. */
function at(x: number, y: number): string {
  return `left:${(x / W) * 100}%;top:${(y / H) * 100}%`;
}

export class SherpaSchematicCard extends LitElement {
  static override properties: PropertyDeclarations = {
    hass: { attribute: false },
    _config: { state: true },
  };

  hass?: Hass;
  private _config?: SchematicCardConfig;

  setConfig(config: SchematicCardConfig): void {
    if (!config) throw new Error('Invalid configuration');
    this._config = { prefix: DEFAULT_PREFIX, ...config };
  }

  static getStubConfig(): SchematicCardConfig {
    return { type: 'custom:sherpa-schematic-card' };
  }

  getCardSize(): number {
    return 6;
  }

  getGridOptions() {
    return { columns: 12, rows: 6, min_columns: 6, min_rows: 4 };
  }

  private get _ids(): Ids {
    return ids(this._config?.prefix);
  }

  override render(): TemplateResult {
    const hass = this.hass;
    const id = this._ids;
    const l = labels(hass, this._config?.labels);
    if (!hass || !hass.states[id.waterOut]) {
      return html`<ha-card>${errorRow(`${l.noUnit} "${this._config?.prefix}".`)}</ha-card>`;
    }

    const mode = str(hass, id.mode);
    const selected = str(hass, id.climate);              // off | heat | cool
    const pumping = isOn(hass, id.pump);
    const running = isOn(hass, id.compressor);
    const route: Route = mode === 'domestic_hot_water' || mode === 'anti_legionella'
      ? 'tank'
      : selected === 'heat' || selected === 'cool' ? 'circuit' : 'none';
    const circuit: Circuit = selected === 'cool' ? 'cool' : 'heat';
    const tank = num(hass, id.dhwTank);
    const tankSet = num(hass, id.dhwSetpoint);
    const target = num(hass, id.waterTarget);
    const targetSource = attr<string>(hass, id.waterTarget, 'source');
    const error = str(hass, id.errorCode);
    const errorText = this._describe(id.errorCode, error);
    const override = str(hass, id.overrideCode);
    const overrideText = this._describe(id.overrideCode, override);
    const supplyAt = route === 'tank'
      ? { x: VALVE.x, y: 268 } : { x: (VALVE.x + 16 + CIRCUIT.x) / 2 - 8, y: VALVE.y - 30 };
    const returnAt = route === 'tank'
      ? { x: 590, y: COIL_OUT } : { x: 600, y: 60 };

    return html`
      <ha-card>
        <div class="head">
          <span class="title">${this._config?.title ?? l.title}</span>
          <span class="chips">
            ${mode ? html`<span class="chip">${l[mode as LabelKey] ?? mode}</span>` : nothing}
            ${isOn(hass, id.defrost) ? html`<span class="chip warn"><ha-icon icon="mdi:snowflake-melt"></ha-icon>${l.defrost}</span>` : nothing}
            ${isOn(hass, id.night) ? html`<span class="chip"><ha-icon icon="mdi:weather-night"></ha-icon>${l.night}</span>` : nothing}
            ${isOn(hass, id.eh1) ? html`<span class="chip running">EH1</span>` : nothing}
            ${isOn(hass, id.eh2) ? html`<span class="chip running">EH2</span>` : nothing}
            ${isOn(hass, id.k5) ? html`<span class="chip running">K5</span>` : nothing}
          </span>
        </div>
        <div class="stage">
          ${this._drawing(route, circuit, pumping, running, tank, tankSet)}
          <span class="pill" style=${at(FAN.x, ODU.y + 24)}>
            <span class="readout-pill"><ha-icon icon="mdi:thermometer"></ha-icon>${fmt(num(hass, id.outdoor))} °C</span>
          </span>
          <span class="pill" style=${at(FAN.x, ODU.y + ODU.h - 30)}>
            <span class="readout-pill">
              <span class="dot ${running ? 'on' : ''}"></span>${l.compressor}
            </span>
          </span>
          <span class="label strong" style=${at(ODU.x + ODU.w / 2, ODU.y - 18)}>${l.outdoorUnit}</span>
          <span class="label strong" style=${at(IDU.x + IDU.w / 2, IDU.y + 26)}>${l.indoorUnit}</span>
          ${HEATERS.map((h, i) => html`
            <span class="label tiny ${isOn(hass, i === 0 ? id.eh1 : id.eh2) ? 'on' : ''}" style=${at(h.x, h.y)}>EH${i + 1}</span>`)}
          <span class="pill" style=${at(supplyAt.x, supplyAt.y)}>
            <span class="readout-pill" title=${l.supply}><ha-icon icon="mdi:arrow-right-thin"></ha-icon>${fmt(num(hass, id.waterOut))} °C</span>
          </span>
          <span class="pill" style=${at(returnAt.x, returnAt.y)}>
            <span class="readout-pill" title=${l.return}><ha-icon icon="mdi:arrow-left-thin"></ha-icon>${fmt(num(hass, id.waterIn))} °C</span>
          </span>
          <span class="label strong" style=${at(CIRCUIT.x + CIRCUIT.w / 2, CIRCUIT.y + 32)}>
            ${circuit === 'cool' ? l.coolingCircuit : l.circuit}
          </span>
          <span class="pill" style=${at(CIRCUIT.x + CIRCUIT.w / 2, CIRCUIT.y + 74)}>
            <span class="readout-pill" title=${targetSource?.endsWith('_curve') ? l.calculated : l.fixed}>
              ${l.target} ${fmt(target)} °C${targetSource?.endsWith('_curve') ? ' *' : ''}
            </span>
          </span>
          <span class="label strong" style=${at(TANK.x + TANK.w / 2, TANK.y + 26)}>${l.tank}</span>
          <span class="pill" style=${at(TANK.x + TANK.w / 2, TANK.y + 60)}>
            <span class="readout-pill big">${fmt(tank)} °C</span>
          </span>
          <span class="label" style=${at(TANK.x + TANK.w / 2, TANK.y + 88)}>${l.set} ${fmt(tankSet)} °C</span>
        </div>
        ${error && error !== 'none' ? html`<div class="fault">${errorText}</div>` : nothing}
        ${override && override !== 'none' ? html`<div class="override">${overrideText}</div>` : nothing}
        ${targetSource?.endsWith('_curve') ? html`<div class="foot muted">* ${l.calculated}</div>` : nothing}
      </ha-card>
    `;
  }

  /** "E07 UE communication error": the code with the manual's text, from the sensor's attributes. */
  private _describe(entity: string, codes: string | undefined): string {
    const texts = attr<Record<string, string>>(this.hass, entity, 'descriptions') ?? {};
    return (codes ?? '').split(',').map((code) => code.trim()).filter(Boolean)
      .map((code) => (texts[code] ? `${code} ${texts[code]}` : code)).join(' · ');
  }

  private _drawing(route: Route, circuit: Circuit, pumping: boolean, running: boolean,
                   tank: number | undefined, tankSet: number | undefined): TemplateResult {
    const live = route === 'tank'
      ? { supply: t.WATER.dhw, back: t.WATER.dhwReturn }
      : circuit === 'cool'
        ? { supply: t.WATER.coolSupply, back: t.WATER.coolReturn }
        : { supply: t.WATER.heatSupply, back: t.WATER.heatReturn };
    const idle = t.GREY.track;
    const pipe = (d: string, colour: string, flowing: boolean) => svg`
      <path d=${d} fill="none" stroke=${colour} stroke-width=${t.PIPE_W}
            stroke-linecap="round" stroke-linejoin="round" />
      ${flowing ? svg`<path class="flow" d=${d} fill="none" stroke="#ffffff"
            stroke-opacity="0.45" stroke-width=${t.PIPE_W * 0.45}
            stroke-dasharray="10 16" stroke-linecap="round" />` : nothing}
    `;
    const toCircuit = route === 'circuit';
    const toTank = route === 'tank';
    // How far the tank has come up towards its setpoint, from 15 degC.
    const fill = tank === undefined || tankSet === undefined || tankSet <= 15
      ? 0 : Math.max(0, Math.min(1, (tank - 15) / (tankSet - 15)));
    const inner = TANK.h - 8;

    return html`
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Sherpa schematic">
        <defs>
          <clipPath id="tank-clip">
            <rect x=${TANK.x + 4} y=${TANK.y + 4} width=${TANK.w - 8} height=${inner} rx="30" />
          </clipPath>
        </defs>

        <!-- refrigerant link -->
        ${[ODU.y + 85, ODU.y + 145].map((y) => svg`
          <line x1=${ODU.x + ODU.w} y1=${y} x2=${IDU.x} y2=${y}
                stroke=${running ? t.RUNNING : t.GREY.dark} stroke-opacity=${running ? 0.7 : 1}
                stroke-width=${t.DETAIL_W * 1.6} stroke-dasharray=${running ? '2 7' : 'none'}
                stroke-linecap="round" class=${running ? 'flow slow' : ''} />`)}

        <!-- pipes, idle first so the live route draws over the junctions -->
        ${pipe(PIPES.toCircuit, toCircuit ? live.supply : idle, toCircuit && pumping)}
        ${pipe(PIPES.circuitReturn, toCircuit ? live.back : idle, toCircuit && pumping)}
        ${pipe(PIPES.toTank, toTank ? live.supply : idle, toTank && pumping)}
        ${pipe(PIPES.tankReturn, toTank ? live.back : idle, toTank && pumping)}
        ${pipe(PIPES.supply, route === 'none' ? idle : live.supply, route !== 'none' && pumping)}

        <!-- outdoor unit -->
        <rect x=${ODU.x} y=${ODU.y} width=${ODU.w} height=${ODU.h} rx="16"
              fill=${t.BODY} stroke=${t.BORDER} stroke-width=${t.OUTLINE_W} />
        <circle cx=${FAN.x} cy=${FAN.y} r=${FAN.r} fill="none" stroke=${t.GREY.dark}
                stroke-width=${t.OUTLINE_W} />
        <g class=${running ? 'spin' : ''} style="transform-origin:${FAN.x}px ${FAN.y}px">
          ${[0, 120, 240].map((a) => svg`
            <ellipse cx=${FAN.x} cy=${FAN.y - 28} rx="12" ry="27"
                     fill=${running ? t.GREY.light : t.GREY.dim}
                     transform="rotate(${a} ${FAN.x} ${FAN.y})" />`)}
          <circle cx=${FAN.x} cy=${FAN.y} r="9" fill=${t.GREY.mid} />
        </g>

        <!-- indoor unit -->
        <rect x=${IDU.x} y=${IDU.y} width=${IDU.w} height=${IDU.h} rx="16"
              fill=${t.BODY} stroke=${t.BORDER} stroke-width=${t.OUTLINE_W} />
        ${HEATERS.map((h, i) => svg`
          <rect x=${h.x - 28} y=${h.y - 15} width="56" height="30" rx="8"
                fill=${isOn(this.hass, i === 0 ? this._ids.eh1 : this._ids.eh2) ? t.RUNNING : 'none'}
                stroke=${isOn(this.hass, i === 0 ? this._ids.eh1 : this._ids.eh2) ? t.RUNNING : t.GREY.dark}
                stroke-width=${t.DETAIL_W} />`)}
        <circle cx=${PUMP.x} cy=${PUMP.y} r=${PUMP.r}
                fill=${pumping ? t.RUNNING : 'none'}
                stroke=${pumping ? t.RUNNING : t.GREY.dim} stroke-width=${t.OUTLINE_W} />
        <path d="M ${PUMP.x - 7} ${PUMP.y - 10} L ${PUMP.x + 11} ${PUMP.y} L ${PUMP.x - 7} ${PUMP.y + 10} Z"
              fill=${pumping ? t.ACCENT_INK : t.GREY.dim} />

        <!-- three-way valve: inlet left, circuit right, tank down -->
        ${this._valve(toCircuit ? live.supply : undefined, toTank ? live.supply : undefined)}

        <!-- circuit -->
        <rect x=${CIRCUIT.x} y=${CIRCUIT.y} width=${CIRCUIT.w} height=${CIRCUIT.h} rx="14"
              fill=${t.BODY} stroke=${toCircuit ? live.supply : t.BORDER}
              stroke-width=${t.OUTLINE_W} />

        <!-- tank, filled as far as it has come up towards its setpoint -->
        <rect x=${TANK.x} y=${TANK.y} width=${TANK.w} height=${TANK.h} rx="34"
              fill=${t.BODY} stroke=${toTank ? t.WATER.dhw : t.BORDER} stroke-width=${t.OUTLINE_W} />
        <rect x=${TANK.x} y=${TANK.y + 4 + inner * (1 - fill)} width=${TANK.w}
              height=${inner * fill} fill=${t.WATER.dhw} fill-opacity="0.16"
              clip-path="url(#tank-clip)" />
        <path d=${COIL} fill="none" stroke=${toTank ? t.WATER.dhw : t.GREY.dark}
              stroke-width=${t.DETAIL_W * 1.4} stroke-linecap="round" />
      </svg>
    `;
  }

  private _valve(circuit?: string, tank?: string): TemplateResult {
    const { x, y } = VALVE;
    const s = 16;
    const port = (points: string, colour?: string) => svg`
      <polygon points=${points} fill=${colour ?? t.BODY}
               stroke=${colour ?? t.GREY.dim} stroke-width=${t.DETAIL_W} stroke-linejoin="round" />`;
    return svg`
      ${port(`${x - s},${y - 10} ${x - s},${y + 10} ${x},${y}`, circuit ?? tank)}
      ${port(`${x + s},${y - 10} ${x + s},${y + 10} ${x},${y}`, circuit)}
      ${port(`${x - 10},${y + s} ${x + 10},${y + s} ${x},${y}`, tank)}
    `;
  }

  /*
   * The schematic is artwork: it always sits on the dark ground and everything
   * on it takes fixed colours, as on the Futura schematics -- a light theme
   * would otherwise print dark captions on the dark equipment.
   *
   * The overlays are HTML over a scaling SVG. At a flat 12px they collide once
   * the card is narrower than the ~508px stage they were laid out at, so each
   * is min(its size, the size that scales with the stage): 12px at 508px is
   * 2.36cqw. Padding and gaps are in em, so a pill shrinks as one piece.
   */
  static override styles = [
    sharedStyles,
    css`
      ha-card {
        background: ${cssVal(t.GROUND)};
        color: ${cssVal(t.INK)};
        --sherpa-text: ${cssVal(t.INK)};
        --sherpa-muted: ${cssVal(t.DIM)};
        --sherpa-panel: rgba(255, 255, 255, 0.08);
      }

      .stage {
        position: relative;
        container-type: inline-size;
      }

      svg {
        display: block;
        width: 100%;
        height: auto;
      }

      .pill,
      .label {
        position: absolute;
        transform: translate(-50%, -50%);
        white-space: nowrap;
        pointer-events: none;
      }

      .pill {
        pointer-events: auto;
      }

      .stage .readout-pill {
        font-size: min(12px, 2.36cqw);
        padding: 0.33em 0.67em;
        gap: 0.5em;
        border-radius: 1.1em;
      }

      .stage .readout-pill ha-icon {
        --mdc-icon-size: 1.1em;
      }

      .stage .readout-pill.big {
        font-size: min(14px, 2.75cqw);
      }

      .label {
        font-size: min(11px, 2.17cqw);
        color: ${cssVal(t.DIM)};
      }

      .label.strong {
        font-size: min(12px, 2.36cqw);
        color: ${cssVal(t.INK)};
      }

      .label.tiny {
        font-size: min(10px, 1.97cqw);
        font-weight: 500;
      }

      .label.tiny.on {
        color: ${cssVal(t.ACCENT_INK)};
      }

      .dot {
        width: 0.6em;
        height: 0.6em;
        border-radius: 50%;
        background: var(--sherpa-neutral);
      }

      .dot.on {
        background: var(--sherpa-running);
      }

      .fault,
      .override {
        margin-top: 10px;
        padding: 8px 10px;
        border-radius: 10px;
        font-size: 0.85rem;
      }

      .fault {
        background: color-mix(in srgb, var(--sherpa-fault) 22%, transparent);
        color: #ff7b70;
      }

      .override {
        background: color-mix(in srgb, var(--sherpa-warn) 25%, transparent);
      }

      .foot {
        margin-top: 6px;
        font-size: 0.75rem;
      }

      .flow {
        animation: flow 1.6s linear infinite;
      }

      .flow.slow {
        animation-duration: 3s;
      }

      .spin {
        animation: spin 1.4s linear infinite;
      }

      @keyframes flow {
        to {
          stroke-dashoffset: -52;
        }
      }

      @keyframes spin {
        to {
          transform: rotate(360deg);
        }
      }
    `,
  ];
}
