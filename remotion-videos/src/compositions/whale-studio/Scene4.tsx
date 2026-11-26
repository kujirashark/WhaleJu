import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from 'remotion';
import { BRAND, TYPO, STEPS } from './constants';
import { sceneFadeOut, Tag, pulse } from './utils';
const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };
const ICONS = ['✎', '✓', '◈', '⚿', '▤', '▶', '◉', '⇩'];
export const Scene4: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const out = sceneFadeOut(frame, durationInFrames);
  const line = interpolate(frame, [0, 40], [0, 1], clamp);
  return (
    <AbsoluteFill style={{ background: BRAND.bg, opacity: out, padding: '70px 90px', justifyContent: 'center' }}>
      <div style={{ marginBottom: 60 }}><Tag>八步流程 · 全程对话陪跑</Tag></div>
      <div style={{ position: 'relative', height: 260 }}>
        {/* 时间轴主线 */}
        <div style={{
          position: 'absolute', top: 78, left: 40, right: 40, height: 2,
          background: BRAND.accent, transform: `scaleX(${line})`, transformOrigin: 'left',
          opacity: 0.5,
        }} />
        <div style={{ display: 'flex', justifyContent: 'space-between', position: 'relative' }}>
          {STEPS.map((s, i) => {
            const on = interpolate(frame, [10 + i * 18, 25 + i * 18], [0, 1], clamp);
            const isCurrent = frame > 10 + i * 18 && frame < 20 + (i + 1) * 18;
            const ring = isCurrent ? pulse(frame, 1.05, 0.08, 30) : 1;
            return (
              <div key={s} style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center',
                width: 170, opacity: on,
              }}>
                <div style={{
                  width: 60, height: 60, borderRadius: '50%',
                  background: BRAND.surface2,
                  border: `2px solid ${BRAND.accent}`,
                  display: 'grid', placeItems: 'center',
                  fontSize: 24, color: BRAND.accent,
                  transform: `scale(${ring})`,
                  boxShadow: isCurrent ? `0 0 24px ${BRAND.accent}88` : 'none',
                }}>{ICONS[i]}</div>
                <div style={{
                  marginTop: 18, fontSize: 24, color: BRAND.text,
                  fontFamily: BRAND.mono, textAlign: 'center',
                }}>{s}</div>
                <div style={{
                  marginTop: 6, fontSize: 16, color: BRAND.accent, fontFamily: BRAND.mono,
                }}>STEP {String(i + 1).padStart(2, '0')}</div>
              </div>
            );
          })}
        </div>
      </div>
      <div style={{
        fontSize: TYPO.body, color: BRAND.text2, marginTop: 40, textAlign: 'center',
      }}>
        从一句话到成片，每一步都给你看清楚
      </div>
    </AbsoluteFill>
  );
};
