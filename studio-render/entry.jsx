import React from 'react';
import { AbsoluteFill, Audio, Composition, Img, Sequence, interpolate, registerRoot, useCurrentFrame, useVideoConfig } from 'remotion';
import { cameraSvg } from './camera.mjs';

function Scene({ scene, index, total, audio }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const duration = Math.round(scene.duration_seconds * fps);
  const opacity = scene.transition === 'cut' ? 1 : interpolate(frame, [0, 8, duration - 8, duration], [0, 1, 1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const camera = scene.visual?.camera_transition;
  const cameraProgress = camera ? Math.max(0, Math.min(1, frame / Math.max(1, duration - 1))) : 0;
  const sceneSvg = cameraSvg(scene.visual_svg, scene.visual, cameraProgress);
  return <AbsoluteFill style={{ backgroundColor: '#112a32', color: '#fbf7ef', fontFamily: 'sans-serif', padding: 48 }}>
    <div style={{ fontSize: 24, letterSpacing: 3, color: '#bacdc8' }}>IGNIS-ATLASSIA / FROZEN STUDY BRIEFING</div>
    <div style={{ opacity, transform: scene.transition === 'slide' ? `translateX(${interpolate(frame, [0, 10], [25, 0], { extrapolateRight: 'clamp' })}px)` : undefined }}>
      <h1 style={{ fontSize: 42, margin: '20px 0 14px' }}>{scene.title}</h1>
      <div><Img src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(sceneSvg)}`} style={{ display: 'block', width: 1360, height: 765, objectFit: 'contain', margin: '0 auto', borderRadius: 12 }} /></div>
    </div>
    <div style={{ position: 'absolute', left: 52, right: 52, bottom: 36, background: '#112a32', padding: '18px 28px', borderTop: '2px solid #3b5b63', fontSize: 28 }}>
      <div>{scene.caption}</div><div style={{ display: 'flex', justifyContent: 'space-between', color: '#bacdc8', fontSize: 18, marginTop: 10 }}><span>NASA FIRMS observations · schematic views · UTC dates</span><span>{index + 1} / {total}</span></div>
    </div>
    {audio?.src ? <Audio src={audio.src} /> : null}
  </AbsoluteFill>;
}
function Documentary({ resolved, preparedAudio = [] }) {
  const { fps } = useVideoConfig();
  return <AbsoluteFill>{resolved.scenes.map((scene, index) => <Sequence key={scene.chapter_id} from={Math.round(scene.start_seconds * fps)} durationInFrames={Math.round((scene.start_seconds + scene.duration_seconds) * fps) - Math.round(scene.start_seconds * fps)}><Scene scene={scene} index={index} total={resolved.scenes.length} audio={preparedAudio.find((segment) => segment.chapter_id === scene.chapter_id)} /></Sequence>)}</AbsoluteFill>;
}
function Root() {
  return <Composition id="Briefing" component={Documentary} width={1920} height={1080} fps={30} durationInFrames={60} defaultProps={{ resolved: { scenes: [] } }} calculateMetadata={({ props }) => ({ durationInFrames: Math.round(props.resolved.profile.duration_seconds * 30) })} />;
}
registerRoot(Root);
