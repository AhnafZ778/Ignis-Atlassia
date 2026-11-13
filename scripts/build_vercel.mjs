/** Tiny public entry point. Application cookies and APIs stay on Render. */
import {mkdir,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';

let target;
try {target=new URL(process.env.FIREATLAS_RENDER_URL || '');} catch {throw Error('Set FIREATLAS_RENDER_URL to your deployed Render HTTPS origin.');}
if(target.protocol!=='https:' || target.username || target.password || !target.hostname || target.port || !['','/'].includes(target.pathname) || target.search || target.hash || !/^[a-z0-9.-]+$/i.test(target.hostname))
 throw Error('FIREATLAS_RENDER_URL must be an HTTPS origin without a path, port, query, fragment or credentials.');
if(target.origin===`https://${process.env.VERCEL_URL}` || target.origin===`https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`)
 throw Error('Use the Render origin, not this Vercel origin, to avoid a redirect loop.');
const origin=target.origin;
const output=fileURLToPath(new URL('../deployment/vercel-dist/',import.meta.url));
await mkdir(output,{recursive:true});
// Origin contains only validated ASCII hostname syntax. Never embed private env.
await writeFile(output+'index.html',`<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>Opening Ignis-Atlassia</title></head>
<body><main><h1>Ignis-Atlassia</h1><p>Opening the scientific whiteboard…</p><p><a href="${origin}/studio-excalidraw.html">Open the whiteboard</a></p></main>
<script>location.replace(${JSON.stringify(origin)}+location.pathname+location.search+location.hash);</script></body></html>\n`);
console.log('Built public Vercel entry page; the application remains on one Render origin.');
