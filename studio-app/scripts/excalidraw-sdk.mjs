// Build the exact pinned public helpers for the local export worker.
import {build} from 'esbuild';
await build({stdin:{contents:"export {convertToExcalidrawElements,restoreElements,serializeAsJSON} from '@excalidraw/excalidraw';",resolveDir:process.cwd()},bundle:true,format:'esm',platform:'node',target:'node22',outfile:'../fireatlas/static/studio-assets/excalidraw-sdk.mjs',loader:{'.css':'empty'},define:{'import.meta.env.DEV':'false'},logLevel:'error'});
