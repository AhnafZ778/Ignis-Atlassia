/** Assemble real AI& clips, preserving authentic chart overlays and complete checked narration. */
import { readFile, writeFile, lstat, realpath } from 'node:fs/promises';
import { resolve, join, relative } from 'node:path';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { checkInput } from './input.mjs';
import { checkAudioFiles } from './audio.mjs';
import { muxSubtitles } from './subtitles.mjs';
const directory = resolve(process.argv[2]);
const input = checkInput(JSON.parse(await readFile(join(directory, 'input.json'), 'utf8')));
const native = JSON.parse(await readFile(join(directory, 'native-clips.json'), 'utf8'));
await checkAudioFiles(directory, input);
const cache = await realpath(resolve(directory, '../../aiand-video-cache'));
const quote = file => file.replaceAll("'", "'\\''");
function run(args) {
  const response = spawnSync('ffmpeg', ['-v', 'error', '-y', ...args], { encoding: 'utf8', timeout: 120000, maxBuffer: 1000000 });
  if (response.status !== 0) throw new Error('AI& film composition failed: '+(response.stderr || '').slice(-200));
}
const clips = [];
process.stdout.write('PHASE encoding\n');
for (const [index, scene] of input.resolved.scenes.entries()) {
  const item = native.clips[index];
  if (!item || item.chapter_id !== scene.chapter_id) throw new Error('Native clip scope disagrees with the saved chapter.');
  const path = await realpath(item.path), stat = await lstat(item.path);
  if (relative(cache, path).startsWith('..') || stat.isSymbolicLink() || !stat.isFile() || stat.size > 512*1024*1024 || createHash('sha256').update(await readFile(path)).digest('hex') !== item.sha256) throw new Error('Invalid or changed native video.');
  const probe = spawnSync('ffprobe', ['-v', 'error', '-protocol_whitelist', 'file,pipe', '-show_entries', 'stream=codec_type:format=duration', '-of', 'json', path], { encoding: 'utf8', timeout: 10000 });
  if (probe.status !== 0) throw new Error('AI& video could not be decoded.');
  const media = JSON.parse(probe.stdout);
  if (!media.streams.some(s => s.codec_type === 'video') || !media.streams.some(s => s.codec_type === 'audio')) throw new Error('AI& did not supply its expected video and sound tracks.');
  const segments = input.audio.filter(a => a.chapter_id === scene.chapter_id).sort((a,b) => a.index-b.index);
  const target = join(directory, 'frames', `native-${index}.mp4`);
  const args = ['-protocol_whitelist', 'file,pipe', '-i', path, '-loop', '1', '-i', join(directory, 'frames', `overlay-${index}.png`)];
  let sound = '[0:a]apad[a]';
  if (segments.length) {
    const list = join(directory, 'frames', `voice-${index}.txt`);
    await writeFile(list, segments.map(a => `file '${quote(join(directory,'audio',a.file))}'`).join('\n'));
    args.push('-f', 'concat', '-safe', '0', '-i', list);
    sound = '[0:a]volume=0.10,apad[amb];[2:a]apad[voice];[amb][voice]amix=inputs=2:duration=longest:normalize=0[a]';
  }
  args.push('-filter_complex', `[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0xf5f4ee,fps=30,tpad=stop_mode=clone:stop_duration=300[bg];[bg][1:v]overlay=0:0:format=auto[v];${sound}`,
    '-map','[v]','-map','[a]','-t',String(scene.duration_seconds),'-c:v','libx264','-threads','2','-filter_complex_threads','2','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-ac','1',target);
  run(args);
  clips.push(`file '${quote(target)}'`);
  process.stdout.write(`PROGRESS ${(index+1)/input.resolved.scenes.length*.9}\n`);
}
await writeFile(join(directory, 'frames', 'native-list.txt'), clips.join('\n'));
run(['-f','concat','-safe','0','-i',join(directory,'frames','native-list.txt'),'-c','copy','-movflags','+faststart',join(directory,'briefing.mp4')]);
await muxSubtitles(directory);
process.stdout.write('PROGRESS 1\n');
