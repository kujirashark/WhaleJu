import React from 'react';
import { AbsoluteFill, Sequence, Audio, staticFile, interpolate, useCurrentFrame } from 'remotion';
import { Scene1 } from './Scene1';
import { Scene2 } from './Scene2';
import { Scene3 } from './Scene3';
import { Scene4 } from './Scene4';
import { Scene5 } from './Scene5';
import { Scene6 } from './Scene6';
import { Scene7 } from './Scene7';
import { Scene8 } from './Scene8';
import { Scene9 } from './Scene9';
import { TIMING, SCENE_STARTS, TOTAL_FRAMES } from './constants';
// ============ AUDIO CONSTANT（替换 BGM 只改这一行）============
const BGM_FILE = 'disharmonic_-_On_The_Moon__Trip_Hop_mix_.ogg';
const BGM_VOLUME = 0.18;
// ============================================================
const SCENES = [Scene1, Scene2, Scene3, Scene4, Scene5, Scene6, Scene7, Scene8, Scene9];
export const WhaleStudioComposition: React.FC = () => {
  return (
    <AbsoluteFill style={{ backgroundColor: '#0d1420' }}>
      {/* BGM：循环播放，最后 90 帧淡出 */}
      <Audio
        src={staticFile(BGM_FILE)}
        startFrom={0}
        volume={(f) =>
          interpolate(f, [0, 30], [0, BGM_VOLUME], {
            extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
          }) *
          interpolate(f, [TOTAL_FRAMES - 90, TOTAL_FRAMES], [1, 0], {
            extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
          })
        }
      />
      {SCENES.map((Scene, i) => (
        <Sequence
          key={i}
          from={SCENE_STARTS[i]}
          durationInFrames={TIMING.scenes[i]}
          premountFor={30}
        >
          <Scene />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
