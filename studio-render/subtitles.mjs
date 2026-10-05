/** Embed the frozen caption file without re-encoding images/audio or changing story timing. */
import { readFile, rename, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

export async function muxSubtitles(directory) {
  const captions = join(directory, 'captions.vtt');
  const bytes = await readFile(captions);
  if (bytes.length > 1000000 || !bytes.toString('utf8').startsWith('WEBVTT\n')) throw new Error('Missing or oversized frozen captions.');
  const video = join(directory, 'briefing.mp4'), temporary = join(directory, 'subtitled.mp4');
  try {
    const result = spawnSync('ffmpeg', ['-v', 'error', '-y', '-i', video, '-i', captions,
      '-map', '0:v:0', '-map', '0:a?', '-map', '1:0', '-c:v', 'copy', '-c:a', 'copy', '-c:s', 'mov_text',
      '-metadata:s:s:0', 'language=eng', '-metadata:s:s:0', 'title=Frozen story narration',
      '-disposition:s:0', 'default', '-movflags', '+faststart', temporary],
    { encoding: 'utf8', maxBuffer: 1000000, timeout: 60000 });
    if (result.status !== 0) throw new Error('Frozen subtitle embedding failed: ' + (result.stderr || '').slice(-200));
    await rename(temporary, video);
  } finally {
    await rm(temporary, { force: true });
  }
}
