/** One isolated local Chromium session, via its private debugging pipe. */
import { spawn } from 'node:child_process';
export async function rasterizer(executable, directory) {
  const child = spawn(executable, ['--headless', '--no-sandbox', '--disable-gpu', '--no-first-run', '--disable-background-networking', '--hide-scrollbars', '--disable-dev-shm-usage', '--force-device-scale-factor=1', '--remote-debugging-pipe', '--user-data-dir=' + directory], { stdio: ['ignore', 'ignore', 'ignore', 'pipe', 'pipe'] });
  const pending = new Map(); let sequence = 0, input = '';
  child.stdio[4].on('data', (chunk) => {
    input += chunk.toString();
    let at;
    while ((at = input.indexOf('\0')) !== -1) {
      const message = JSON.parse(input.slice(0, at)); input = input.slice(at + 1);
      const call = pending.get(message.id);
      if (call) { pending.delete(message.id); clearTimeout(call.timer); message.error ? call.reject(new Error('Chromium could not prepare the frame.')) : call.resolve(message.result); }
    }
  });
  child.once('exit', () => { for (const call of pending.values()) { clearTimeout(call.timer); call.reject(new Error('Chromium closed before frame preparation finished.')); } pending.clear(); });
  const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error('Chromium frame preparation timed out.')); }, 15000);
    pending.set(id, { resolve, reject, timer });
    child.stdio[3].write(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }) + '\0');
  });
  try {
    const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
    const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
    const call = (method, params) => send(method, params, sessionId);
    await call('Page.enable');
    await call('Emulation.setDeviceMetricsOverride', { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
    return {
      async load(svg, { transparent = false } = {}) {
        await call('Emulation.setDefaultBackgroundColorOverride', { color: { r: 245, g: 244, b: 238, a: transparent ? 0 : 1 } });
        const { frameTree } = await call('Page.getFrameTree');
        await call('Page.setDocumentContent', { frameId: frameTree.frame.id, html: '<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;width:1920px;height:1080px;overflow:hidden;background:' + (transparent ? 'transparent' : '#f5f4ee') + '}body>svg{width:1920px;height:1080px;display:block}</style></head><body>' + svg + '</body></html>' });
        await call('Runtime.evaluate', { expression: 'Promise.all([document.fonts.ready,...Array.from(document.images).map(i=>i.decode().catch(()=>{}))])', awaitPromise: true });
      },
      async capture(motion, matrix) {
        const expression = `(()=>{const g=document.querySelector('[data-film-motion]');g.setAttribute('opacity',${motion.opacity});g.setAttribute('transform','translate(0 ${motion.y})');const m=document.querySelector('[data-map-camera]');if(m&&${Boolean(matrix)})m.setAttribute('transform',${JSON.stringify('matrix('+(matrix || []).join(' ')+')')});})()`;
        await call('Runtime.evaluate', { expression });
        const screenshot = await call('Page.captureScreenshot', { format: 'png', fromSurface: true, captureBeyondViewport: false });
        return Buffer.from(screenshot.data, 'base64');
      },
      async close() { try { await send('Browser.close'); } finally { if (child.exitCode === null) child.kill('SIGTERM'); } },
    };
  } catch (error) { child.kill('SIGKILL'); throw error; }
}
