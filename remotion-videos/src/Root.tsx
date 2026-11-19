import React from 'react';
import { Composition } from 'remotion';
import { WhaleStudioComposition } from './compositions/whale-studio/VideoComposition';
import { TIMING, TOTAL_FRAMES } from './compositions/whale-studio/constants';
export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="whale-studio-explainer"
      component={WhaleStudioComposition}
      durationInFrames={TOTAL_FRAMES}
      fps={TIMING.fps}
      width={1920}
      height={1080}
    />
  );
};
