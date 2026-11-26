import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from 'remotion';
import { BRAND, TYPO, MODE_CARDS } from './constants';
import { sceneFadeOut, Tag, pop } from './utils';
const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };
export const Scene6: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const out = sceneFadeOut(frame, durationInFrames);
  const btn = interpolate(frame, [80, 110], [0, 1], clamp);
  const lines = interpolate(frame, [60, 100], [0, 1], clamp);
  return (
    <AbsoluteFill style={{ background: BRAND.bg, opacity: out, padding: '80px 90px', justifyContent: 'center' }}>
      <div style={{ marginBottom: 46 }}><Tag>双模式供给 · 随时切换</Tag></div>
      <div style={{ display: 'flex', gap: 28, justifyContent: 'center' }}>
        {MODE_CARDS.map((c, i) => {
          const p = pop(frame, fps, i * 20);
          return (
            <div key={c.t} style={{
              width: 440, background: BRAND.surface, borderRadius: 12,
              padding: '40px 36px', opacity: p, transform: `scale(${p})`,
              borderTop: `3px solid ${BRAND.accent}`,
            }}>
              <div style={{ fontSize: 20, color: BRAND.accent, fontFamily: BRAND.mono }}>0{i + 1}</div>
              <div style={{ fontSize: TYPO.h2, color: BRAND.text, fontWeight: 700, marginTop: 16 }}>{c.t}</div>
              <div style={{ fontSize: TYPO.small, color: BRAND.text2, marginTop: 12 }}>{c.d}</div>
            </div>
          );
        })}
      </div>
      {/* 三条汇聚线 + 生成按钮 */}
      <div style={{ position: 'relative', height: 150, marginTop: 20 }}>
        <svg width="1920" height="150" style={{ position: 'absolute', left: -90, top: 0 }}>
          {[280, 960, 1640].map((x, i) => (
            <line key={i} x1={x} y1={0} x2={960} y2={80}
              stroke={BRAND.accent} strokeWidth="2" opacity={lines * 0.5} />
          ))}
        </svg>
        <div style={{
          position: 'absolute', left: '50%', top: 62, transform: `translateX(-50%) scale(${btn})`,
          background: BRAND.accent, color: BRAND.bg,
          fontSize: TYPO.body, fontWeight: 700, fontFamily: BRAND.mono,
          padding: '18px 60px', borderRadius: 10,
        }}>开始生成 ▶</div>
      </div>
    </AbsoluteFill>
  );
};
