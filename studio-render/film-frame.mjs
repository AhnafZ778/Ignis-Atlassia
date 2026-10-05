/** Shared infographic film frame; all visual marks come from prepared evidence. */
import { cameraSvg } from './camera.mjs';
const escape = (text) => String(text || '').replace(/[<>&"']/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&apos;' }[c]));
function lines(text, width = 116) {
  const output = [''];
  for (const word of String(text || '').split(/\s+/)) {
    if (output.at(-1).length + word.length + 1 > width) output.push(word);
    else output[output.length - 1] += (output.at(-1) ? ' ' : '') + word;
  }
  return output.slice(0, 3);
}
export function filmFrame(scene, index, total, progress = 0) {
  const evidence = cameraSvg(scene.visual_svg, scene.visual, progress).replace(/^<svg[^>]*>/, '').replace(/<\/svg>$/, '');
  const caption = lines(scene.caption).map((line, i) => `<text x="88" y="${958+i*30}" fill="#263f4e" font-size="24">${escape(line)}</text>`).join('');
  const title = lines(scene.title, 76).slice(0, 2).map((line, i) => `<text x="88" y="${116+i*42}" fill="#152d3e" font-size="36" font-weight="bold">${escape(line)}</text>`).join('');
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080" font-family="DejaVu Sans, sans-serif">
    <defs><linearGradient id="film-paper" x2="1" y2="1"><stop stop-color="#edf2ff"/><stop offset="1" stop-color="#fff8e9"/></linearGradient></defs>
    <rect width="1920" height="1080" fill="url(#film-paper)"/>
    <circle cx="1760" cy="74" r="220" fill="#b7c7f8" opacity=".19"/>
    <rect width="1920" height="9" fill="#355bd1"/>
    <text x="88" y="66" fill="#4266bd" font-size="20" letter-spacing="4">IGNIS-ATLASSIA / JARVIS STORIES</text>
    ${title}
    <text x="1818" y="66" fill="#60738a" font-size="20" text-anchor="end">${index+1} / ${total}</text>
    <rect x="146" y="165" width="1628" height="748" rx="24" fill="#192d4d" opacity=".08"/>
    <rect x="146" y="157" width="1628" height="748" rx="24" fill="#fffdf8"/>
    <svg x="170" y="180" width="1580" height="712" viewBox="0 0 960 540" preserveAspectRatio="xMidYMid meet">${evidence}</svg>
    ${caption}<text x="88" y="1050" fill="#657487" font-size="17">Frozen scientific evidence · UTC acquisition dates · AI-authored interpretation</text>
    <rect x="1490" y="1037" width="328" height="5" rx="3" fill="#d6def0"/>
    <rect x="1490" y="1037" width="${328*(index+1)/total}" height="5" rx="3" fill="#4768cf"/>
  </svg>`;
}
