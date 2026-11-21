import React from 'react';
import { Composition } from 'remotion';
import { WhaleStudioComposition } from './compositions/whale-studio/VideoComposition';
import { TIMING, TOTAL_FRAMES } from './compositions/whale-studio/constants';
import { DevlogVerticalComposition } from './compositions/devlog-vertical/VideoComposition';
import { TIMING as DEVLOG_TIMING, TOTAL_FRAMES as DEVLOG_FRAMES } from './compositions/devlog-vertical/constants';
export const RemotionRoot: React.FC = () => {
  return (
    <>
      {/* 16:9 产品解说片 */}
      <Composition
        id="whale-studio-explainer"
        component={WhaleStudioComposition}
        durationInFrames={TOTAL_FRAMES}
        fps={TIMING.fps}
        width={1920}
        height={1080}
      />
      {/* 9:16 抖音竖屏 · 开发进度片 */}
      <Composition
        id="whale-devlog-vertical"
        component={DevlogVerticalComposition}
        durationInFrames={DEVLOG_FRAMES}
        fps={DEVLOG_TIMING.fps}
        width={1080}
        height={1920}
      />
    </>
  );
};
