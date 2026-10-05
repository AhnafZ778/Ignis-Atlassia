/** Rendering accepts prepared data only. No arbitrary URLs or code. */
export function checkInput(input) {
  const story = input?.resolved;
  if (!story || story.schema !== 'fireatlas-resolved-story-v1' || !Array.isArray(story.scenes) || !story.scenes.length || story.scenes.length > 24) throw new Error('Unsupported story snapshot.');
  if (story.profile.width !== 1920 || story.profile.height !== 1080 || story.profile.fps !== 30) throw new Error('Only the bounded 1080p/30 landscape profile is supported.');
  let cursor = 0;
  for (const scene of story.scenes) {
    if (!Number.isFinite(scene.duration_seconds) || scene.duration_seconds < 2 || scene.duration_seconds > 300 || Math.abs(scene.start_seconds - cursor) > 0.001) throw new Error('Invalid scene timing.');
    if (typeof scene.visual_svg !== 'string' || scene.visual_svg.length > 2100000 || !scene.visual_svg.startsWith('<svg') || /<script|<foreignObject|\bon\w+\s*=|\bsrc\s*=/i.test(scene.visual_svg)) throw new Error('Only a prepared self-contained SVG is accepted.');
    const links = [...scene.visual_svg.matchAll(/(?:\bxlink:)?\bhref\s*=\s*(["'])(.*?)\1/gi)];
    if (links.length !== [...scene.visual_svg.matchAll(/\bhref\s*=/gi)].length || /<!DOCTYPE|<style\b|url\(\s*(?!#[\w-]+\s*\))/i.test(scene.visual_svg)) throw new Error('Only a prepared self-contained SVG is accepted.');
    for (const match of links) {
      if (!/^data:image\/(?:png|jpeg|webp);base64,[A-Za-z0-9+/]+=*$/.test(match[2])) throw new Error('Only a prepared self-contained image is accepted.');
    }
    const camera = scene.visual?.camera_transition;
    if (camera) {
      for (const box of [camera.from_bbox, camera.to_bbox]) {
        if (!Array.isArray(box) || box.length !== 4 || box.some((value) => typeof value !== 'number' || !Number.isFinite(value))) throw new Error('Invalid prepared camera transition.');
      }
      if (camera.from_bbox[0] >= camera.from_bbox[2] || camera.from_bbox[1] >= camera.from_bbox[3] || camera.to_bbox[0] >= camera.to_bbox[2] || camera.to_bbox[1] >= camera.to_bbox[3]) throw new Error('Invalid prepared camera bounds.');
    }
    if (typeof scene.caption !== 'string' || scene.caption.length > 300 || typeof scene.narration_text !== 'string' || scene.narration_text.length > 2400) throw new Error('Oversized scene text.');
    cursor += scene.duration_seconds;
  }
  if (cursor > 600 || Math.abs(cursor - story.profile.duration_seconds) > 0.001) throw new Error('Invalid total duration.');
  if (input.audio !== undefined && (!Array.isArray(input.audio) || input.audio.length > 100)) throw new Error('Invalid prepared narration inventory.');
  const orders = new Map();
  for (const segment of input.audio || []) {
    if (!/^[a-f0-9]{64}\.mp3$/.test(segment.file) || !/^[a-f0-9]{64}$/.test(segment.sha256) ||
      !Number.isInteger(segment.index) || segment.index < 0 || !story.scenes.some((scene) => scene.chapter_id === segment.chapter_id)) throw new Error('Invalid prepared narration file.');
    const indexes = orders.get(segment.chapter_id) || []; indexes.push(segment.index); orders.set(segment.chapter_id, indexes);
    if (segment.duration_seconds !== undefined && (!Number.isFinite(segment.duration_seconds) || segment.duration_seconds <= 0 || segment.duration_seconds > 300)) throw new Error('Invalid prepared narration duration.');
  }
  for (const indexes of orders.values()) if (indexes.sort((a, b) => a - b).some((index, at) => index !== at)) throw new Error('Incomplete or duplicate narration sequence.');
  return input;
}
