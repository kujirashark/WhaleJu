import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from 'remotion';
import { BRAND, TYPO } from './constants';
import { fadeSlideUp, WhaleMark, pop, pulse } from './utils';
const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };
export const Scene9: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const mark = pop(frame, fps, 0);
  const title = fadeSlideUp(frame, 40, 26);
  const btn = fadeSlideUp(frame, 75, 24);
  const glow = pulse(frame, 0.18, 0.09);
  // 最后 30 帧整体淡出到黑场
  const out = interpolate(frame, [durationInFrames - 30, durationInFrames], [1, 0], clamp);
  return (
    <AbsoluteFill style={{ background: BRAND.bg, opacity: out, justifyContent: 'center', alignItems: 'center' }}>
      <div style={{
        position: 'absolute', width: 700, height: 700, borderRadius: '50%',
        background: `radial-gradient(circle, ${BRAND.accent}22 0%, transparent 62%)`,
        opacity: glow,
      }} />
      <div style={{ transform: `scale(${mark})`, marginBottom: 16 }}>
        <WhaleMark size={96} />
      </div>
      <div style={{ fontSize: TYPO.hero + 6, fontWeight: 700, color: BRAND.text, ...title }}>
        鲸鲨漫剧
      </div>
      <div style={{
        fontSize: TYPO.h1, color: BRAND.accent, fontWeight: 600,
        marginTop: 28, ...title,
      }}>把一生，拍成一部剧</div>
      <div style={{
        marginTop: 56, background: BRAND.accent, color: BRAND.bg,
        fontSize: TYPO.body, fontWeight: 700, padding: '20px 72px',
        borderRadius: 10, fontFamily: BRAND.mono, ...btn,
        boxShadow: `0 0 40px ${BRAND.accent}66`,
      }}>开始创作 →</div>
      <div style={{
        position: 'absolute', bottom: 80, fontSize: 22, color: BRAND.text2,
        fontFamily: BRAND.mono, letterSpacing: '0.1em',
      }}>本地运行 · 数据不出电脑</div>
    </AbsoluteFill>
  );
};
