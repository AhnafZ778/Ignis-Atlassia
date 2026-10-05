import React from 'react';
import { AbsoluteFill, Audio, Composition, Img, Sequence, interpolate, registerRoot, useCurrentFrame, useVideoConfig } from 'remotion';
import { filmFrame } from './film-frame.mjs';

function Scene({ scene, index, total, audio }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const duration = Math.round(scene.duration_seconds * fps);
  const opacity = scene.transition === 'cut' ? 1 : interpolate(frame, [0, 8, duration - 8, duration], [0, 1, 1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const camera = scene.visual?.camera_transition;
  const cameraProgress = camera ? Math.max(0, Math.min(1, frame / Math.max(1, duration - 1))) : 0;
  const sceneSvg = filmFrame(scene, index, total, cameraProgress);
  return <AbsoluteFill style={{ backgroundColor: '#edf2ff' }}>
    <div style={{ opacity, position: 'absolute', inset: 0, transform: scene.transition === 'slide' ? `translateY(${interpolate(frame, [0, 14], [12, 0], { extrapolateRight: 'clamp' })}px)` : undefined }}>
      <Img src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(sceneSvg)}`} style={{ width: 1920, height: 1080, display: 'block' }} />
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
