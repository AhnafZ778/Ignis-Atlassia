import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { muxSubtitles } from './subtitles.mjs';

test('actual MP4 retains picture, sound, frozen subtitle text and timing', async (t) => {
  if (spawnSync('ffmpeg', ['-version']).status !== 0 || spawnSync('ffprobe', ['-version']).status !== 0) return t.skip('ffmpeg/ffprobe are unavailable');
  const directory = await mkdtemp(join(tmpdir(), 'fireatlas-subtitles-'));
  try {
    const video = join(directory, 'briefing.mp4');
    const generated = spawnSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=s=160x90:d=1:r=30',
      '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=mono', '-t', '1', '-c:v', 'libx264', '-threads', '1', '-pix_fmt', 'yuv420p', '-c:a', 'aac', video]);
    assert.equal(generated.status, 0, generated.stderr.toString());
    await writeFile(join(directory, 'captions.vtt'), 'WEBVTT\n\n1\n00:00:00.000 --> 00:00:00.500\n113 cell-days, UTC.\n\n2\n00:00:00.500 --> 00:00:01.000\nUnknown remains unknown.\n');
    const picture = () => spawnSync('ffmpeg', ['-v', 'error', '-i', video, '-map', '0:v:0', '-c', 'copy', '-f', 'hash', '-hash', 'sha256', '-'], { encoding: 'utf8' }).stdout;
    const before = picture();
    await muxSubtitles(directory);
    assert.equal(picture(), before, 'subtitle mux must not change the video stream');
    const probe = spawnSync('ffprobe', ['-v', 'error', '-show_streams', '-of', 'json', video], { encoding: 'utf8' });
    const streams = JSON.parse(probe.stdout).streams;
    assert.deepEqual(streams.map((s) => s.codec_type), ['video', 'audio', 'subtitle']);
    const subtitles = streams.find((s) => s.codec_type === 'subtitle');
    assert.equal(subtitles.codec_name, 'mov_text');
    assert.equal(subtitles.disposition.default, 1);
    assert.equal(subtitles.tags.language, 'eng');
    const extracted = spawnSync('ffmpeg', ['-v', 'error', '-i', video, '-map', '0:s:0', '-f', 'webvtt', '-'], { encoding: 'utf8' }).stdout;
    assert.match(extracted, /00:00\.000 --> 00:00\.500\n113 cell-days, UTC\./);
    assert.match(extracted, /00:00\.500 --> 00:01\.000\nUnknown remains unknown\./);
    const original = await readFile(video);
    await writeFile(join(directory, 'captions.vtt'), 'not frozen captions');
    await assert.rejects(muxSubtitles(directory), /frozen captions/);
    assert.deepEqual(await readFile(video), original, 'failed caption preparation preserves existing video');
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
