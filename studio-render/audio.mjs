/** Recheck controlled local narration before either renderer assembles/trims a chapter. */
import { lstat, readFile, realpath } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { join, resolve, dirname } from 'node:path';
import { spawnSync } from 'node:child_process';

export async function checkAudioFiles(directory, input) {
  if (!input.audio?.length) return;
  const root = await realpath(join(directory, 'audio'));
  const durations = new Map();
  let total = 0;
  for (const segment of input.audio) {
    const path = resolve(root, segment.file), stat = await lstat(path);
    if (stat.isSymbolicLink() || !stat.isFile() || dirname(await realpath(path)) !== root || stat.size <= 0 || stat.size > 8 * 1024 * 1024) throw new Error('Invalid or oversized local narration.');
    total += stat.size;
    if (total > 64 * 1024 * 1024) throw new Error('Local narration exceeds 64 MiB.');
    const content = await readFile(path);
    if (content.length > 8 * 1024 * 1024 || createHash('sha256').update(content).digest('hex') !== segment.sha256) throw new Error('Local narration changed after preparation.');
    const result = spawnSync('ffprobe', ['-v', 'error', '-protocol_whitelist', 'file,pipe', '-f', 'mp3', '-select_streams', 'a:0', '-show_entries', 'stream=codec_type:format=duration', '-of', 'json', path],
      { encoding: 'utf8', timeout: 10000, maxBuffer: 16384 });
    if (result.status !== 0) throw new Error('Cannot verify narration duration. Retry with captions-only rendering.');
    const probe = JSON.parse(result.stdout), duration = Number(probe.format?.duration);
    if (probe.streams?.[0]?.codec_type !== 'audio' || !Number.isFinite(duration) || duration <= 0 || duration > 300 ||
      (segment.duration_seconds !== undefined && Math.abs(segment.duration_seconds - duration) > 0.001)) throw new Error('Narration duration disagrees with its frozen preparation.');
    durations.set(segment.chapter_id, (durations.get(segment.chapter_id) || 0) + duration);
  }
  for (const scene of input.resolved.scenes) {
    if ((durations.get(scene.chapter_id) || 0) > scene.duration_seconds) throw new Error('Narration exceeds its saved chapter. Increase the chapter duration or render with complete captions only.');
  }
}
