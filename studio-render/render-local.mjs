/** Opt-in schematic renderer; consumes the same prepared scenes as Remotion. */
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { checkInput } from './input.mjs';
import { filmFrame } from './film-frame.mjs';
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
const sceneSvg = (scene, index, progress = 0) => filmFrame(scene, index, story.scenes.length, progress);
process.stdout.write('PHASE rendering\n');
for (let index = 0; index < story.scenes.length; index++) {
  const scene = story.scenes[index];
  const sceneImages = [];
  const keyframes = scene.visual?.camera_transition ? [0, 0.5, 1] : [0];
  for (let keyframe = 0; keyframe < keyframes.length; keyframe++) {
    const filename = join(frames, `scene-${index}-${keyframe}.png`), svgfile = join(frames, `scene-${index}-${keyframe}.svg`);
    await writeFile(svgfile, sceneSvg(scene, index, keyframes[keyframe]));
    // Chromium honors nested map transforms and clipping consistently with the
    // web reader. ImageMagick's built-in SVG renderer mishandles these clips.
    const htmlfile = join(frames, `scene-${index}-${keyframe}.html`);
    await writeFile(htmlfile, '<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;width:1920px;height:1080px;overflow:hidden}svg{width:1920px;height:1080px;display:block}</style></head><body>' + sceneSvg(scene, index, keyframes[keyframe]) + '</body></html>');
    run(browser, ['--headless', '--no-sandbox', '--disable-gpu', '--no-first-run', '--disable-background-networking', '--hide-scrollbars', '--disable-dev-shm-usage', '--force-device-scale-factor=1', '--window-size=1920,1080', '--virtual-time-budget=1000', '--user-data-dir=' + join(directory, 'browser-profile'), '--screenshot=' + filename, pathToFileURL(htmlfile).href]);
    const duration = scene.duration_seconds / keyframes.length;
    sceneImages.push(`file '${quote(filename)}'\nduration ${duration}`);
  }
  const finalImage = join(frames, `scene-${index}-${keyframes.length-1}.png`);
  sceneImages.push(`file '${quote(finalImage)}'`);
  const sceneList = join(frames, `scene-${index}.txt`), clip = join(frames, `scene-${index}.mp4`);
  await writeFile(sceneList, sceneImages.join('\n'));
  const fade = scene.transition === 'cut' ? '' : `,fade=t=in:st=0:d=0.45,fade=t=out:st=${Math.max(0, scene.duration_seconds-.45)}:d=0.45`;
  run('ffmpeg', ['-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', sceneList,
    '-t', String(scene.duration_seconds), '-vf', `tpad=stop_mode=clone:stop_duration=1,fps=30,scale=1920:1080${fade}`,
    '-frames:v', String(Math.round(scene.duration_seconds*30)), '-c:v', 'libx264', '-threads', '2', '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p', clip]);
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
  process.stdout.write(`PROGRESS ${0.05 + 0.25 * ((index + 1) / story.scenes.length)}\n`);
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
