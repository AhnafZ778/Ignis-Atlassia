/** Editorial film frame. Scientific marks remain the prepared frozen figure. */
import { cameraSvg } from './camera.mjs';
const escape = (text) => String(text ?? '').replace(/[<>&"']/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&apos;' }[c]));
function lines(text, width, limit = 5) {
  const output = [''];
  for (const word of String(text || '').split(/\s+/)) {
    if (output.at(-1).length && output.at(-1).length + word.length + 1 > width) output.push('');
    output[output.length - 1] += (output.at(-1) ? ' ' : '') + word;
  }
  return output.slice(0, limit);
}
export function filmMotion(seconds, duration, transition = 'fade') {
  const intro = Math.max(0, Math.min(1, seconds / .9));
  const ease = 1 - (1 - intro) ** 3;
  const outro = transition === 'cut' ? 1 : Math.max(0, Math.min(1, (duration - seconds) / .35));
  return { opacity: Math.min(ease, outro), y: 18 * (1 - ease) };
}
function figure(svg) {
  // Remove only the duplicated editorial headline and tiny UI card badges.
  // Scope, original values, legends, axes and source marks stay intact.
  return svg.replace(/^<svg[^>]*>/, '').replace(/<\/svg>$/, '')
    .replace(/<text x="32" y="(?:40|42)"[^>]*>[^<]*<\/text>/, '')
    .replace(/<rect x="(?:650|795)" y="(?:22|53)" width="134" height="24"[^>]*\/>/g, '')
    .replace(/<text x="(?:657|802)" y="(?:38|69)"[^>]*>[^<]*<\/text>/g, '')
    .replace('<rect width="960" height="540" fill="#fbf7ef"/>', '<rect width="960" height="540" fill="#fcfbf7"/>');
}
export function filmFrame(scene, index, total, progress = 0, seconds = 2) {
  const evidence = figure(cameraSvg(scene.visual_svg, scene.visual, progress));
  const title = lines(scene.title, 54, 2).map((line, i) => `<text x="104" y="${158+i*65}" fill="#182e38" font-size="58" font-weight="600">${escape(line)}</text>`).join('');
  const caption = lines(scene.caption, 31, 8).map((line, i) => `<text x="104" y="${365+i*34}" fill="#324d56" font-size="25">${escape(line)}</text>`).join('');
  const fields = (scene.resolved_fields || []).filter((f) => f.value !== null && ['string', 'number'].includes(typeof f.value)).slice(0, 2);
  const facts = fields.map((f, i) => {
    const label = f.method_id === 'assistant-original-records-v1' && f.path === '/total' ? 'Original source records' : f.label || 'Checked value';
    const value = lines(String(f.value), 24, 2).map((line, j) => `<text x="104" y="${708+i*104+j*30}" fill="#173e54" font-size="26" font-weight="600">${escape(line)}</text>`).join('');
    return `<text x="104" y="${681+i*104}" fill="#5e7075" font-size="16">${escape(label.slice(0, 36))}</text>${value}<text x="104" y="${742+i*104}" fill="#5e7075" font-size="18">${escape(String(f.unit || 'Checked evidence').slice(0, 37))}</text>`;
  }).join('');
  const motion = filmMotion(seconds, scene.duration_seconds || 16, scene.transition);
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080" font-family="DejaVu Sans, sans-serif">
    <rect width="1920" height="1080" fill="#f5f4ee"/>
    <rect x="104" y="65" width="24" height="24" rx="12" fill="#416cdb"/>
    <text x="148" y="85" fill="#516367" font-size="20" letter-spacing="3">IGNIS-ATLASSIA · FIELD NOTES</text>
    <text x="1816" y="85" fill="#64777b" font-size="20" text-anchor="end">${String(index+1).padStart(2,'0')} / ${String(total).padStart(2,'0')}</text>
    <g data-film-motion="true" opacity="${motion.opacity}" transform="translate(0 ${motion.y})">
      ${title}
      <rect x="104" y="285" width="52" height="4" rx="2" fill="#d19c44"/>
      <text x="104" y="324" fill="#758187" font-size="16" letter-spacing="3">IN THIS VIEW</text>
      ${caption}
      ${fields.length ? '<text x="104" y="638" fill="#758187" font-size="16" letter-spacing="3">SOURCE RECEIPT</text>' : ''}${facts}
      <rect x="559" y="264" width="1257" height="708" rx="18" fill="#e9e9e1"/>
      <rect x="551" y="256" width="1257" height="708" rx="18" fill="#fcfbf7"/>
      <svg x="567" y="272" width="1225" height="676" viewBox="0 0 960 540" preserveAspectRatio="xMidYMid meet">${evidence}</svg>
    </g>
    <path d="M104 1005H1816" stroke="#d7ddd7"/>
    <text x="104" y="1047" fill="#66777a" font-size="16">Frozen evidence · UTC acquisition dates · AI-authored narration</text>
    <rect x="1516" y="1034" width="300" height="4" rx="2" fill="#d7ddd7"/>
    <rect x="1516" y="1034" width="${300*(index+1)/total}" height="4" rx="2" fill="#416cdb"/>
  </svg>`;
}
