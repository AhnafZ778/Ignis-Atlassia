import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';

test('native composition keeps real video motion, audio, checked graphics and subtitles', async t => {
  if (spawnSync('ffmpeg',['-version']).status !== 0) return t.skip('ffmpeg unavailable');
  const root = await mkdtemp(join(tmpdir(), 'native-film-'));
  const job = join(root,'renders','job'), cache = join(root,'aiand-video-cache');
  await mkdir(join(job,'frames'),{recursive:true}); await mkdir(cache);
  try {
    const clip = join(cache,'clip.mp4');
    let result = spawnSync('ffmpeg',['-v','error','-y','-f','lavfi','-i','testsrc2=size=384x216:rate=30:duration=2','-f','lavfi','-i','sine=frequency=440:duration=2','-c:v','libx264','-c:a','aac','-threads','2',clip]);
    assert.equal(result.status,0,result.stderr.toString());
    const png = join(job,'frames','overlay-0.png');
    result = spawnSync('ffmpeg',['-v','error','-y','-f','lavfi','-i','color=c=ivory@0.3:s=1920x1080,format=rgba','-frames:v','1','-threads','1',png]);
    assert.equal(result.status,0,result.stderr.toString());
    const input = {resolved:{schema:'fireatlas-resolved-story-v1',profile:{width:1920,height:1080,fps:30,duration_seconds:2},
      scenes:[{chapter_id:'a',start_seconds:0,duration_seconds:2,caption:'Frozen evidence',narration_text:'Checked source',visual_svg:'<svg></svg>'}]},audio:[]};
    await writeFile(join(job,'input.json'),JSON.stringify(input));
    await writeFile(join(job,'native-clips.json'),JSON.stringify({clips:[{chapter_id:'a',path:clip,sha256:createHash('sha256').update(await readFile(clip)).digest('hex')}]}));
    await writeFile(join(job,'captions.vtt'),'WEBVTT\n\n00:00.000 --> 00:02.000\nChecked source\n');
    result=spawnSync('node',[resolve('compose-aiand.mjs'),job],{encoding:'utf8',timeout:30000});
    assert.equal(result.status,0,result.stderr);
    const probe=spawnSync('ffprobe',['-v','error','-show_entries','stream=codec_type,width,height:format=duration','-of','json',join(job,'briefing.mp4')],{encoding:'utf8'});
    const media=JSON.parse(probe.stdout);
    assert.deepEqual(media.streams.map(s=>s.codec_type),['video','audio','subtitle']);
    assert.equal(media.streams[0].width,1920);
    assert.ok(Math.abs(Number(media.format.duration)-2)<.1);
    await writeFile(clip,Buffer.from('changed remote output'));
    result=spawnSync('node',[resolve('compose-aiand.mjs'),job],{encoding:'utf8',timeout:30000});
    assert.notEqual(result.status,0);
    assert.match(result.stderr,/changed native video/);
  } finally { await rm(root,{recursive:true,force:true}); }
});
