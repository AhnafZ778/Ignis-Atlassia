import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { checkAudioFiles } from './audio.mjs';
import { checkInput } from './input.mjs';

test('real local narration must fit its saved chapter and preserve recorded bytes', async (t) => {
  if (spawnSync('ffmpeg', ['-version']).status !== 0 || spawnSync('ffprobe', ['-version']).status !== 0) return t.skip('Optional local media tools are unavailable');
  const directory = await mkdtemp(join(tmpdir(), 'fireatlas-audio-'));
  try {
    await mkdir(join(directory, 'audio'));
    const file = 'a'.repeat(64) + '.mp3', path = join(directory, 'audio', file);
    const generated = spawnSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', '-c:a', 'libmp3lame', path]);
    assert.equal(generated.status, 0, generated.stderr.toString());
    const original = await readFile(path);
    const item = { file, chapter_id: 'a', index: 0, sha256: createHash('sha256').update(original).digest('hex') };
    const input = { audio: [item], resolved: { schema: 'fireatlas-resolved-story-v1', profile: { width: 1920, height: 1080, fps: 30, duration_seconds: 2 },
      scenes: [{ chapter_id: 'a', start_seconds: 0, duration_seconds: 2, caption: '', narration_text: 'Local fixture, not generated speech.', visual_svg: '<svg></svg>' }] } };
    assert.equal(checkInput(input), input);
    await checkAudioFiles(directory, input);
    await assert.rejects(checkAudioFiles(directory, { ...input, resolved: { scenes: [{ chapter_id: 'a', duration_seconds: .5 }] } }), /exceeds its saved chapter/);
    await assert.rejects(checkAudioFiles(directory, { ...input, audio: [{ ...item, duration_seconds: 10 }] }), /disagrees/);
    for (const audio of ([item, item], [{ ...item, index: 1 }], [{ ...item, duration_seconds: Infinity }])) assert.throws(() => checkInput({ ...input, audio }), /narration/);
    await writeFile(path, Buffer.concat([original, Buffer.from('changed')]));
    await assert.rejects(checkAudioFiles(directory, input), /changed after preparation/);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
