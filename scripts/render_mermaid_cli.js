#!/usr/bin/env node
/* Render all Mermaid .mmd diagrams in docs/diagrams to SVG and PNG using mermaid-cli (mmdc).
 *
 * Usage:
 *   npm run diagrams
 *   npm run diagrams:chrome   # uses CHROME_PATH env var if set
 *
 * Environment:
 *   CHROME_PATH (optional) - absolute path to Chrome/Chromium executable
 *                             used when running with --use-chrome flag
 */

const { spawnSync } = require('node:child_process');
const { readdirSync, statSync } = require('node:fs');
const { join, extname, basename } = require('node:path');

const DIAGRAMS_DIR = join(process.cwd(), 'docs', 'diagrams');
const USE_CHROME = process.argv.includes('--use-chrome');
const CHROME_PATH = process.env.CHROME_PATH || '';

function listMmdFiles(dir) {
  const entries = readdirSync(dir, { withFileTypes: true });
  return entries
    .filter((ent) => ent.isFile() && extname(ent.name).toLowerCase() === '.mmd')
    .map((ent) => join(dir, ent.name));
}

function runMmdc(input, output, extraEnv = {}) {
  const args = ['-i', input, '-o', output];
  const env = { ...process.env, ...extraEnv };
  const res = spawnSync('mmdc', args, { stdio: 'inherit', env });
  if (res.error) {
    throw res.error;
  }
  if (res.status !== 0) {
    throw new Error(`mmdc exited with code ${res.status}`);
  }
}

function main() {
  try {
    // Validate directory
    const st = statSync(DIAGRAMS_DIR);
    if (!st.isDirectory()) {
      console.error(`Not a directory: ${DIAGRAMS_DIR}`);
      process.exit(1);
    }

    const files = listMmdFiles(DIAGRAMS_DIR);
    if (!files.length) {
      console.error('No .mmd files found in docs/diagrams');
      process.exit(1);
    }

    const extraEnv = {};
    if (USE_CHROME) {
      if (!CHROME_PATH) {
        console.warn('CHROME_PATH not set; attempting to use default Puppeteer Chromium');
      } else {
        // Puppeteer respects this env var for executable path
        extraEnv.PUPPETEER_EXECUTABLE_PATH = CHROME_PATH;
        console.log(`Using Chrome at: ${CHROME_PATH}`);
      }
    }

    for (const file of files) {
      const base = basename(file, '.mmd');
      const svgOut = join(DIAGRAMS_DIR, `${base}.svg`);
      const pngOut = join(DIAGRAMS_DIR, `${base}.png`);

      console.log(`Rendering ${file} -> ${svgOut}`);
      runMmdc(file, svgOut, extraEnv);

      console.log(`Rendering ${file} -> ${pngOut}`);
      runMmdc(file, pngOut, extraEnv);
    }

    console.log(`Rendered ${files.length} diagram(s) to SVG and PNG.`);
  } catch (err) {
    console.error(`Render failed: ${err.message || err}`);
    process.exit(1);
  }
}

main();
