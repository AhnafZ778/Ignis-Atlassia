/** Prepare authenticated first-frame references and exact transparent evidence overlays. */
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { checkInput } from './input.mjs';
import { filmFrame } from './film-frame.mjs';
import { rasterizer } from './chromium.mjs';
const directory = resolve(process.argv[2]);
const input = checkInput(JSON.parse(await readFile(join(directory, 'input.json'), 'utf8')));
const browser = ['chromium', 'chromium-browser', 'google-chrome'].find(n => spawnSync(n, ['--version']).status === 0);
if (!browser) throw new Error('Chromium is required for exact evidence reference images.');
await mkdir(join(directory, 'frames'), { recursive: true });
const painter = await rasterizer(browser, join(directory, 'browser-profile'));
try {
  for (const [index, scene] of input.resolved.scenes.entries()) {
    const svg = filmFrame(scene, index, input.resolved.scenes.length);
    await painter.load(svg);
    await writeFile(join(directory, 'frames', `reference-${index}.png`), await painter.capture({ opacity: 1, y: 0 }));
    const overlay = svg.replace('<rect width="1920" height="1080" fill="#f5f4ee"/>', `<rect width="1920" height="1080" fill="#f5f4ee" opacity=".32"/>
      <rect width="1920" height="104" fill="#f5f4ee" opacity=".97"/>
      <rect x="80" y="108" width="1756" height="132" rx="16" fill="#fcfbf7" opacity=".97"/>
      <rect x="80" y="268" width="450" height="668" rx="16" fill="#fcfbf7" opacity=".97"/>
      <rect y="984" width="1920" height="96" fill="#f5f4ee" opacity=".97"/>`)
      .replace('Frozen evidence · UTC acquisition dates · AI-authored narration', 'AI& generated motion · Exact frozen evidence overlay · Checked narration');
    await painter.load(overlay, { transparent: true });
    await writeFile(join(directory, 'frames', `overlay-${index}.png`), await painter.capture({ opacity: 1, y: 0 }));
  }
} finally { await painter.close(); }
