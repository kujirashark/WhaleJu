import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from 'remotion';
import { BRAND, TYPO, PAINS } from './constants';
import { staggerIn, sceneFadeOut, Tag } from './utils';
const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };
export const Scene2: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const out = sceneFadeOut(frame, durationInFrames);
  return (
    <AbsoluteFill style={{ background: BRAND.bg, opacity: out, padding: '80px 110px', justifyContent: 'center' }}>
      <div style={{ marginBottom: 46 }}>
        <Tag>做剧的人，都卡在这三件事</Tag>
      </div>
      {PAINS.map((p, i) => {
        const s = staggerIn(frame, i, 30, 10);
        const bar = interpolate(frame, [10 + i * 30, 35 + i * 30], [0, 6], clamp);
        return (
          <div key={p} style={{
            display: 'flex', alignItems: 'center', gap: 28,
            background: BRAND.surface, borderRadius: 10,
            padding: '26px 32px', marginBottom: 22,
            opacity: s.opacity, transform: s.transform,
          }}>
            <div style={{ width: bar, height: 44, background: BRAND.danger, borderRadius: 3 }} />
            <div style={{
              fontFamily: BRAND.mono, fontSize: 22, color: BRAND.danger, width: 44,
            }}>0{i + 1}</div>
            <div style={{ fontSize: TYPO.h2, color: BRAND.text, fontWeight: 600 }}>{p}</div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
