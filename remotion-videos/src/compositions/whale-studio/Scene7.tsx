import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from 'remotion';
import { BRAND, TYPO } from './constants';
import { fadeSlideUp, sceneFadeOut, pulse } from './utils';
const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };
export const Scene7: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const out = sceneFadeOut(frame, durationInFrames);
  const local = fadeSlideUp(frame, 30, 30);
  const caption = fadeSlideUp(frame, 75, 26);
  const shield = pulse(frame, 1, 0.04, 50);
  return (
    <AbsoluteFill style={{ background: BRAND.bg, opacity: out, justifyContent: 'center', alignItems: 'center' }}>
      {/* 中央电脑 + LOCAL 屏障 */}
      <div style={{ position: 'relative', width: 520, height: 340, display: 'grid', placeItems: 'center', transform: `scale(${shield})` }}>
        <svg width="360" height="300" viewBox="0 0 360 300" fill="none">
          <rect x="50" y="30" width="260" height="170" rx="10" stroke={BRAND.accent} strokeWidth="3" fill={BRAND.surface} />
          <path d="M20 220h320l-20 40H40z" stroke={BRAND.accent} strokeWidth="3" fill={BRAND.surface2} />
          <path d="M150 200h60v20h-60z" fill={BRAND.surface2} stroke={BRAND.accent} strokeWidth="2" />
          {/* 三条向外的数据流，被屏障弹回 */}
          <path d="M50 90h-30M310 90h30M180 30V5" stroke={BRAND.text2} strokeWidth="2" strokeDasharray="6 6" />
          <circle cx="20" cy="90" r="6" fill={BRAND.danger} />
          <circle cx="340" cy="90" r="6" fill={BRAND.danger} />
          <circle cx="180" cy="5" r="6" fill={BRAND.danger} />
        </svg>
        <div style={{
          position: 'absolute', fontSize: 44, fontFamily: BRAND.mono, fontWeight: 700,
          color: BRAND.accent, background: BRAND.bg, padding: '8px 28px',
          border: `2px solid ${BRAND.accent}`, borderRadius: 8,
          letterSpacing: '0.15em',
        }}>LOCAL</div>
      </div>
      <div style={{ fontSize: 92, fontWeight: 700, color: BRAND.text, fontFamily: BRAND.mono, ...local }}>
        数据不出电脑
      </div>
      <div style={{ fontSize: TYPO.h2, color: BRAND.text2, marginTop: 24, ...caption }}>
        密钥和素材，只留在你的电脑里
      </div>
    </AbsoluteFill>
  );
};
