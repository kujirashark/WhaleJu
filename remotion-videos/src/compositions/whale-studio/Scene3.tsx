import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from 'remotion';
import { BRAND, TYPO } from './constants';
import { fadeSlideUp, sceneFadeOut, WhaleMark, pop, pulse } from './utils';
const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };
export const Scene3: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const out = sceneFadeOut(frame, durationInFrames);
  const mark = pop(frame, fps, 0);
  const name = fadeSlideUp(frame, 42, 24);
  const tag = fadeSlideUp(frame, 72, 24);
  const glow = pulse(frame, 0.22, 0.1);
  // 四角青色装饰角标
  const corner = (top: boolean, left: boolean) => ({
    position: 'absolute' as const,
    [top ? 'top' : 'bottom']: 90,
    [left ? 'left' : 'right']: 110,
    width: 32, height: 32,
    borderTop: top ? `2px solid ${BRAND.accent}` : 'none',
    borderBottom: top ? 'none' : `2px solid ${BRAND.accent}`,
    borderLeft: left ? `2px solid ${BRAND.accent}` : 'none',
    borderRight: left ? 'none' : `2px solid ${BRAND.accent}`,
    opacity: interpolate(frame, [20, 45], [0, 0.7], clamp),
  });
  return (
    <AbsoluteFill style={{ background: BRAND.bg, opacity: out, justifyContent: 'center', alignItems: 'center' }}>
      <div style={corner(true, true)} />
      <div style={corner(true, false)} />
      <div style={corner(false, true)} />
      <div style={corner(false, false)} />
      <div style={{
        position: 'absolute', width: 560, height: 560, borderRadius: '50%',
        background: `radial-gradient(circle, ${BRAND.accent}22 0%, transparent 65%)`,
        opacity: glow,
      }} />
      <div style={{ transform: `scale(${mark})`, marginBottom: 24 }}>
        <WhaleMark size={120} />
      </div>
      <div style={{ fontSize: TYPO.hero + 6, fontWeight: TYPO.weight, color: BRAND.text, ...name }}>
        鲸鲨漫剧
      </div>
      <div style={{
        fontSize: TYPO.h2, color: BRAND.accent, fontFamily: BRAND.mono,
        letterSpacing: '0.08em', marginTop: 20, ...tag,
      }}>
        本地优先 · AI 漫剧制片台
      </div>
    </AbsoluteFill>
  );
};
