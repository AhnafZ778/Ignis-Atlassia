import { createHash } from 'node:crypto';
import { cp, mkdir, readdir, readFile, writeFile } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const rootPath = fileURLToPath(new URL('../../fireatlas/static/studio-assets/', import.meta.url));
const files = {};
await cp(fileURLToPath(new URL('../node_modules/@excalidraw/excalidraw/dist/prod/fonts', import.meta.url)), join(rootPath, 'fonts'), { recursive: true });

async function walk(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) await walk(path);
    else if (entry.name !== 'studio-manifest.json') {
      const bytes = await readFile(path);
      const name = relative(rootPath, path).split('\\').join('/');
      files[name] = { sha256: createHash('sha256').update(bytes).digest('hex'), bytes: bytes.byteLength };
    }
  }
}

await mkdir(rootPath, { recursive: true });
await walk(rootPath);
const entry = Object.keys(files).find((name) => name.startsWith('assets/studio-') && name.endsWith('.js'));
if (!entry) throw new Error('Vite did not produce the Studio entry module.');
const viteManifest = JSON.parse(await readFile(join(rootPath, '.vite/manifest.json'), 'utf8'));
const entryMeta = Object.values(viteManifest).find((item) => item.isEntry && item.file === entry);
const bootstrap = (entryMeta?.css || []).map((name) => `const link${(entryMeta.css || []).indexOf(name)} = document.createElement('link'); link${(entryMeta.css || []).indexOf(name)}.rel = 'stylesheet'; link${(entryMeta.css || []).indexOf(name)}.href = new URL(${JSON.stringify('./' + name)}, import.meta.url).href; document.head.append(link${(entryMeta.css || []).indexOf(name)});`).join('\n') + `\nimport './${entry}';\n`;
const bootstrapPath = join(rootPath, 'studio-entry.js');
await writeFile(bootstrapPath, bootstrap);
const bootstrapBytes = await readFile(bootstrapPath);
files['studio-entry.js'] = { sha256: createHash('sha256').update(bootstrapBytes).digest('hex'), bytes: bootstrapBytes.byteLength };
const sceneMeta = Object.values(viteManifest).find((item) => item.isEntry && item.name === 'excalidraw');
if (!sceneMeta) throw new Error('Missing Excalidraw editor entry.');
const sceneBootstrap = (sceneMeta.css || []).map((name, i) => `const css${i}=document.createElement('link');css${i}.rel='stylesheet';css${i}.href=new URL(${JSON.stringify('./' + name)},import.meta.url).href;document.head.append(css${i});`).join('\n') + `\nimport './${sceneMeta.file}';\n`;
await writeFile(join(rootPath, 'excalidraw-entry.js'), sceneBootstrap);
const sceneBytes = Buffer.from(sceneBootstrap);
files['excalidraw-entry.js'] = { sha256: createHash('sha256').update(sceneBytes).digest('hex'), bytes: sceneBytes.byteLength };
await writeFile(join(rootPath, 'features.json'), JSON.stringify({ schema: 'fireatlas-studio-features-v1', tldraw: true, reactflow: true, liveblocks: true }, null, 2));
const featureBytes = await readFile(join(rootPath, 'features.json'));
files['features.json'] = { sha256: createHash('sha256').update(featureBytes).digest('hex'), bytes: featureBytes.byteLength };
await writeFile(join(rootPath, 'studio-manifest.json'), JSON.stringify({ schema: 'fireatlas-studio-assets-v1', generated_by: 'studio-app', files }, null, 2));
