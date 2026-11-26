import React from 'react';
import { AbsoluteFill, Audio, Sequence, staticFile } from 'remotion';
import { BGM, SCENE_STARTS, TIMING } from './constants';
import { Scene1 } from './Scene1';
import { Scene2 } from './Scene2';
import { Scene3 } from './Scene3';
import { Scene4 } from './Scene4';
import { Scene5 } from './Scene5';
import { Scene6 } from './Scene6';
import { Scene7 } from './Scene7';
import { Scene8 } from './Scene8';
import { Scene9 } from './Scene9';
import { AiBadge } from './utils';
const SCENES = [Scene1, Scene2, Scene3, Scene4, Scene5, Scene6, Scene7, Scene8, Scene9];
export const DevlogVerticalComposition: React.FC = () => {
  return (
    <AbsoluteFill style={{ backgroundColor: '#0d1420' }}>
      {SCENES.map((S, i) => (
        <Sequence
          key={i}
          from={SCENE_STARTS[i]}
          durationInFrames={TIMING.scenes[i]}
          premountFor={30}
        >
          <S />
        </Sequence>
      ))}
      {/* 背景音乐：ccMixter CC BY 2.5，发布时需署名（见发布文案） */}
      <Audio src={staticFile(BGM)} volume={0.22} />
      {/* 全片常驻 AI 生成标识（平台合规要求） */}
      <AiBadge opacity={0.85} />
    </AbsoluteFill>
  );
};
