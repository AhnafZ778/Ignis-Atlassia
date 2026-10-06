/** Opt-in schematic renderer; consumes the same prepared scenes as Remotion. */
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { resolve, join } from 'node:path';
import { checkInput } from './input.mjs';
import { filmFrame, filmMotion } from './film-frame.mjs';
import { cameraMatrix } from './camera.mjs';
import { rasterizer } from './chromium.mjs';
import { muxSubtitles } from './subtitles.mjs';
import { checkAudioFiles } from './audio.mjs';
const directory = resolve(process.argv[2] || '');
const bytes = await readFile(join(directory, 'input.json'));
if (bytes.length > 32000000) throw new Error('Prepared render input exceeds 32 MB.');
const input = checkInput(JSON.parse(bytes.toString('utf8')));
process.stdout.write('PHASE preparing-assets\n');
await checkAudioFiles(directory, input);
const { resolved: story, audio } = input;
const frames = join(directory, 'frames'); await mkdir(frames, { recursive: true });
const esc = (text) => String(text || '').replace(/[<>&"']/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&apos;' }[c]));
const quote = (file) => file.replaceAll("'", "'\\''");
function run(command, args) { const result = spawnSync(command, args, { encoding: 'utf8', maxBuffer: 2000000 }); if (result.status !== 0) throw new Error(`${command} failed: ${(result.stderr || '').slice(-300)}`); }
const sounds = [], clips = [];
const browser = ['chromium', 'chromium-browser', 'google-chrome'].find((name) => spawnSync(name, ['--version'], { encoding: 'utf8' }).status === 0);
if (!browser) throw new Error('Local SVG rendering needs Chromium or Google Chrome.');
const painter = await rasterizer(browser, join(directory, 'browser-profile'));
try {
process.stdout.write('PHASE rendering\n');
for (let index = 0; index < story.scenes.length; index++) {
  const scene = story.scenes[index];
  const sceneImages = [];
  await painter.load(filmFrame(scene, index, story.scenes.length));
  const count = Math.round(scene.duration_seconds * 30);
  // Animate entrances/outros at every output frame. Hold a stable scientific
  // figure in between. Explicit map-camera motion is sampled at all 30 fps.
  const moments = scene.visual?.camera_transition ? Array.from({length: count}, (_, i) => i) :
    [...Array.from({length: Math.min(28, count)}, (_, i) => i),
     ...Array.from({length: Math.min(12, count-28)}, (_, i) => count-12+i)];
  for (let at = 0; at < moments.length; at++) {
    const frame = moments[at], seconds = frame / 30;
    const filename = join(frames, `scene-${index}-${frame}.png`);
    const matrix = scene.visual?.camera_transition ? cameraMatrix(scene.visual, frame / Math.max(1, count-1)) : null;
    await writeFile(filename, await painter.capture(filmMotion(seconds, scene.duration_seconds, scene.transition), matrix));
    const until = moments[at+1] ?? count;
    sceneImages.push(`file '${quote(filename)}'\nduration ${(until-frame)/30}`);
  }
  const finalImage = join(frames, `scene-${index}-${moments.at(-1)}.png`);
  sceneImages.push(`file '${quote(finalImage)}'`);
  const sceneList = join(frames, `scene-${index}.txt`), clip = join(frames, `scene-${index}.mp4`);
  await writeFile(sceneList, sceneImages.join('\n'));
  run('ffmpeg', ['-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', sceneList,
    '-t', String(scene.duration_seconds), '-vf', 'tpad=stop_mode=clone:stop_duration=1,fps=30,scale=1920:1080',
    '-frames:v', String(Math.round(scene.duration_seconds*30)), '-c:v', 'libx264', '-threads', '2', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', clip]);
  clips.push(`file '${quote(clip)}'`);
  if (audio?.length) {
    const target = join(frames, `scene-${index}.wav`);
    const segments = audio.filter((a) => a.chapter_id === scene.chapter_id).sort((a, b) => a.index - b.index);
    if (segments.length) {
      const list = join(frames, `audio-${index}.txt`);
      await writeFile(list, segments.map((a) => `file '${quote(join(directory, 'audio', a.file))}'`).join('\n'));
      run('ffmpeg', ['-v', 'error', '-y', '-protocol_whitelist', 'file,pipe', '-f', 'concat', '-safe', '0', '-i', list, '-af', 'apad', '-t', String(scene.duration_seconds), '-ar', '48000', '-ac', '1', target]);
    } else run('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=mono', '-t', String(scene.duration_seconds), target]);
    sounds.push(`file '${quote(target)}'`);
  }
  process.stdout.write(`PROGRESS ${0.05 + 0.8 * ((index + 1) / story.scenes.length)}\n`);
}
const imageList = join(frames, 'clips.txt'); await writeFile(imageList, clips.join('\n'));
const silent = join(directory, audio?.length ? 'silent.mp4' : 'briefing.mp4');
process.stdout.write('PHASE encoding\n');
run('ffmpeg', ['-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', imageList, '-t', String(story.profile.duration_seconds), '-c:v', 'copy', '-movflags', '+faststart', silent]);
if (sounds.length) {
  const soundList = join(frames, 'sounds.txt'); await writeFile(soundList, sounds.join('\n'));
  run('ffmpeg', ['-v', 'error', '-y', '-i', silent, '-f', 'concat', '-safe', '0', '-i', soundList, '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-t', String(story.profile.duration_seconds), '-movflags', '+faststart', join(directory, 'briefing.mp4')]);
}
await muxSubtitles(directory);
process.stdout.write('PROGRESS 1\n');

} finally { await painter.close(); }
