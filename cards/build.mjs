/** Bundle the cards into the single file the integration serves. */
import { build, context } from 'esbuild';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const outfile = resolve(
  here,
  '../custom_components/olimpia_sherpa_modbus/www/sherpa-cards.js',
);

/** A strict CSP applies in Home Assistant, so everything must be inlined. */
const options = {
  entryPoints: [resolve(here, 'src/index.ts')],
  outfile,
  bundle: true,
  format: 'esm',
  target: 'es2021',
  minify: true,
  sourcemap: false,
  legalComments: 'none',
  banner: { js: '/* Olimpia Splendid Sherpa Lovelace cards - generated, do not edit */' },
};

if (process.argv.includes('--watch')) {
  const ctx = await context(options);
  await ctx.watch();
  console.log(`watching -> ${outfile}`);
} else {
  await build(options);
  console.log(`built -> ${outfile}`);
}
