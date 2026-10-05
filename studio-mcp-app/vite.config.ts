import { defineConfig, type Plugin } from 'vite';
import { fileURLToPath } from 'node:url';
// One static HTML resource for the sandboxed MCP host. No remote scripts, fonts or SDK loading.
function selfContained(): Plugin {
  return { name: 'fireatlas-self-contained-resource', enforce: 'post', generateBundle(_, bundle) {
    const page = bundle['index.html'];
    if (!page || page.type !== 'asset') throw new Error('Missing MCP Apps HTML resource.');
    let html = String(page.source);
    for (const [name, output] of Object.entries(bundle)) {
      if (output.type === 'chunk') {
        html = html.replace(/<script\b[^>]*src="[^"]+"[^>]*><\/script>/, `<script type="module">${output.code.replace(/<\/script/gi, '<\\/script')}</script>`);
        delete bundle[name];
      } else if (name.endsWith('.css')) {
        html = html.replace(/<link\b[^>]*href="[^"]+\.css"[^>]*>/, `<style>${String(output.source)}</style>`);
        delete bundle[name];
      }
    }
    page.source = html;
  } };
}
export default defineConfig({ plugins: [selfContained()], build: { outDir: fileURLToPath(new URL('../fireatlas/static/studio-mcp/', import.meta.url)), emptyOutDir: true, rollupOptions: { input: fileURLToPath(new URL('./index.html', import.meta.url)) } } });
