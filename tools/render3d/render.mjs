// Render a 3D shot (scene3d.html) to transparent PNG frames.
//
//   node render.mjs <shot.json> --stills=20,40 [--out=check/s]        PNG stills to judge the look (seconds each)
//   node render.mjs <shot.json> --clip --dir=<remotion>/public/hero3d  every frame f0..f1 as f####.png (resumable)
//   flags: --spp=N overrides the shot's samples per pixel (64 for drafts, 128-256 for finals)
//
// Chrome comes from the `puppeteer` package (downloaded on npm install). CHROME_PATH points it at
// another Chrome/Chromium. GPU: Metal on macOS; on Linux Chrome picks a backend, override with
// RENDER3D_GL_ARGS="--use-angle=vulkan" (or swiftshader for CPU-only boxes: works, slow).
import puppeteer from 'puppeteer';
import { mkdirSync, writeFileSync, existsSync, statSync, readFileSync } from 'node:fs';
import { dirname, resolve, extname } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const [shotPath, ...rest] = process.argv.slice(2);
if (!shotPath || shotPath.startsWith('--')) { console.log(readFileSync(fileURLToPath(import.meta.url), 'utf8').split('\n').slice(0, 9).join('\n')); process.exit(1); }
const args = Object.fromEntries(rest.map(a => { const [k, v] = a.replace(/^--/, '').split('='); return [k, v ?? true]; }));
const shotDir = dirname(resolve(shotPath));
const cfg = JSON.parse(readFileSync(shotPath, 'utf8'));
if (args.spp) cfg.spp = +args.spp;

for (const o of cfg.objects) {
  if (o.enter !== 'none' && typeof o.in !== 'number') throw new Error(`object ${o.text ?? o.image}: "in" (arrival frame) is required`);
  if (o.image) {
    const p = resolve(shotDir, o.image), ext = extname(p).toLowerCase();
    const mime = ext === '.svg' ? 'image/svg+xml' : ext === '.png' ? 'image/png' : ext === '.webp' ? 'image/webp' : 'image/jpeg';
    o.image = `data:${mime};base64,${readFileSync(p).toString('base64')}`;   // data URL: a file:// image would taint the canvas
  }
}
if (cfg.objects.some(o => o.text != null)) cfg.paths = JSON.parse(readFileSync(resolve(shotDir, cfg.paths || 'paths.json'), 'utf8'));

const gl = process.env.RENDER3D_GL_ARGS ? process.env.RENDER3D_GL_ARGS.split(' ')
  : process.platform === 'darwin' ? ['--use-angle=metal'] : ['--enable-unsafe-swiftshader'];
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_PATH || undefined, headless: true, protocolTimeout: 0,
  args: ['--ignore-gpu-blocklist', '--enable-gpu-rasterization', '--disable-gpu-watchdog',
    '--disable-renderer-backgrounding', '--disable-background-timer-throttling', ...gl],
});
const page = await browser.newPage();
page.on('console', m => { if (['error', 'warn'].includes(m.type())) console.log('[page]', m.text()); });
page.on('pageerror', e => console.log('[page error]', e.message));
await page.setViewport({ width: Math.min(cfg.width, 1600), height: Math.min(cfg.height, 1600) });
await page.evaluateOnNewDocument(c => { window.CFG = c; }, cfg);
await page.goto(pathToFileURL(resolve(HERE, 'scene3d.html')).href, { waitUntil: 'load' });
await page.waitForFunction('window.ready === true || window.failed', { timeout: 180000 });
const failed = await page.evaluate(() => window.failed);
if (failed) { console.error('scene failed to build:', failed); await browser.close(); process.exit(1); }
console.log('GPU:', await page.evaluate(() => gpuInfo()));
const frameAt = async f => { const url = await page.evaluate(f => renderAt(f), f); return Buffer.from(url.slice(url.indexOf(',') + 1), 'base64'); };

if (args.stills) {
  const base = resolve(args.out || 'check/s');
  mkdirSync(dirname(base), { recursive: true });
  for (const s of String(args.stills).split(',').map(Number)) {
    const t0 = Date.now(), f = `${base}_${s}.png`;
    writeFileSync(f, await frameAt(s));
    console.log(f, ((Date.now() - t0) / 1000).toFixed(1), 's');
  }
} else if (args.clip) {
  const dir = resolve(args.dir || 'frames'); mkdirSync(dir, { recursive: true });
  const a = +(args.f0 ?? cfg.f0), b = +(args.f1 ?? cfg.f1);
  if (!Number.isFinite(a) || !Number.isFinite(b)) throw new Error('set f0/f1 in the shot or pass --f0 --f1');
  const start = Date.now(); let done = 0;
  for (let i = a; i <= b; i++) {
    const f = `${dir}/f${String(i).padStart(4, '0')}.png`;
    if (existsSync(f) && statSync(f).size > 200) continue;
    writeFileSync(f, await frameAt(i)); done++;
    if (done % 10 === 0 || i === b) console.log(`frame ${i}/${b}  ${((Date.now() - start) / done / 1000).toFixed(2)} s/frame`);
  }
} else {
  console.log('nothing to do: pass --stills=... or --clip');
}
await browser.close();
