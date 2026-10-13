/**
 * Entry point: registers the elements and their Lovelace picker entries.
 *
 * Registration is explicit rather than via Lit's `@customElement` decorator, for
 * the reason the Futura cards found: esbuild's minifier can tree-shake the
 * decorator calls, leaving a module that loads cleanly and defines nothing.
 */
import { SherpaControlCard } from './control-card';
import { SherpaSchematicCard } from './schematic-card';
import { ACCENT_INK, RUNNING } from './tokens';

export { SherpaControlCard, SherpaSchematicCard };

interface CardRegistration {
  type: string;
  name: string;
  description: string;
  preview?: boolean;
}

const CARDS: Array<CardRegistration & { element: CustomElementConstructor }> = [
  {
    type: 'sherpa-schematic-card',
    name: 'Sherpa schematic',
    description:
      'Outdoor and indoor unit, the three-way valve, the heating circuit and the hot-water '
      + 'tank, with the water route the heat pump is using now.',
    preview: true,
    element: SherpaSchematicCard,
  },
  {
    type: 'sherpa-control-card',
    name: 'Sherpa status and setpoints',
    description:
      'The mode as the panel has it, the water against its target, the climatic curve and '
      + 'the setpoints -- editable where the integration allows writes.',
    preview: true,
    element: SherpaControlCard,
  },
];

const registry = ((window as any).customCards ||= []);

for (const card of CARDS) {
  // A reload of the module must not throw on an already-defined element.
  if (!customElements.get(card.type)) {
    customElements.define(card.type, card.element);
  }
  if (!registry.some((entry: CardRegistration) => entry.type === card.type)) {
    const { element: _element, ...entry } = card;
    registry.push(entry);
  }
}

// eslint-disable-next-line no-console
console.info(
  `%c SHERPA-CARDS %c ${CARDS.length} cards registered `,
  `background:${RUNNING};color:${ACCENT_INK}`,
  '',
);
