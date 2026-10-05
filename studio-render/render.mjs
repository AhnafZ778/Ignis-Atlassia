import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join, resolve } from 'node:path';
import { bundle } from '@remotion/bundler';
import { renderMedia, selectComposition, makeCancelSignal } from '@remotion/renderer';
import { checkInput } from './input.mjs';
import { muxSubtitles } from './subtitles.mjs';
import { checkAudioFiles } from './audio.mjs';

if (!['free-eligible', 'company-license'].includes(process.env.FIREATLAS_REMOTION_LICENSE_ACK)) throw new Error('Set the operator Remotion license acknowledgement before rendering.');
const directory = resolve(process.argv[2] || '');
const bytes = await readFile(join(directory, 'input.json'));
if (bytes.length > 32000000) throw new Error('Prepared render input exceeds 32 MB.');
const input = checkInput(JSON.parse(bytes.toString('utf8')));
process.stdout.write('PHASE preparing-assets\n');
await checkAudioFiles(directory, input);
const preparedAudio = [];
// All segments of a chapter are concatenated before rendering. A chapter
// cannot read arbitrary URLs, and it cannot overlap the next chapter's audio.
if ((input.audio || []).length) {
  const { spawnSync } = await import('node:child_process');
  for (const scene of input.resolved.scenes) {
    const segments = input.audio.filter((a) => a.chapter_id === scene.chapter_id).sort((a, b) => a.index - b.index);
    if (!segments.length) continue;
    const list = join(directory, 'chapter-audio.txt');
    await writeFile(list, segments.map((a) => `file '${join(directory, 'audio', a.file).replaceAll("'", "'\\''")}'`).join('\n'));
    const target = join(directory, 'chapter-audio.mp3');
    const combined = spawnSync('ffmpeg', ['-v', 'error', '-y', '-protocol_whitelist', 'file,pipe', '-f', 'concat', '-safe', '0', '-i', list, '-t', String(scene.duration_seconds), target], { timeout: 30000, maxBuffer: 16000 });
    if (combined.status !== 0) throw new Error('Narration assembly failed. Retry with captions-only rendering.');
    preparedAudio.push({ chapter_id: scene.chapter_id, src: `data:audio/mpeg;base64,${(await readFile(target)).toString('base64')}` });
  }
}
const inputProps = { resolved: input.resolved, preparedAudio };
const serveUrl = await bundle({ entryPoint: fileURLToPath(new URL('./entry.jsx', import.meta.url)), onProgress: (progress) => process.stdout.write(`PROGRESS ${0.05 + progress / 100 * 0.1}\n`) });
const options = { serveUrl, inputProps, browserExecutable: process.env.FIREATLAS_REMOTION_BROWSER || null };
const composition = await selectComposition({ ...options, id: 'Briefing' });
const cancellation = makeCancelSignal();
process.once('SIGTERM', () => cancellation.cancel());
process.stdout.write('PHASE rendering\n');
let encodingAnnounced = false;
await renderMedia({ ...options, composition, codec: 'h264', outputLocation: join(directory, 'briefing.mp4'), concurrency: 2, crf: 22, cancelSignal: cancellation.cancelSignal,
  onProgress: ({ progress, renderedDoneIn }) => {
    if (renderedDoneIn !== null && !encodingAnnounced) { encodingAnnounced = true; process.stdout.write('PHASE encoding\n'); }
    process.stdout.write(`PROGRESS ${0.15 + progress * 0.85}\n`);
  } });
if (!encodingAnnounced) process.stdout.write('PHASE encoding\n');
await muxSubtitles(directory);
process.stdout.write('PROGRESS 1\n');
