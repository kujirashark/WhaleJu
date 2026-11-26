import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from 'remotion';
import { BRAND, TYPO, VALUES } from './constants';
import { sceneFadeOut, countUp, pop } from './utils';
const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };
export const Scene8: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const out = sceneFadeOut(frame, durationInFrames);
  return (
    <AbsoluteFill style={{ background: BRAND.bg, opacity: out, padding: '80px 90px', justifyContent: 'center' }}>
      <div style={{
        fontSize: 22, fontFamily: BRAND.mono, color: BRAND.accent,
        letterSpacing: '0.2em', textAlign: 'center', marginBottom: 60,
      }}>WHAT YOU GET</div>
      <div style={{ display: 'flex', gap: 30, justifyContent: 'center' }}>
        {VALUES.map((v, i) => {
          const p = pop(frame, fps, i * 22);
          const n = countUp(frame, v.num, 10 + i * 22, 45);
          const isZero = v.num === 0;
          return (
            <div key={i} style={{
              width: 500, background: BRAND.surface, borderRadius: 12,
              padding: '56px 40px', textAlign: 'center',
              opacity: p, transform: `scale(${p})`,
              borderBottom: `3px solid ${isZero ? BRAND.gold : BRAND.accent}`,
            }}>
              <div style={{
                fontSize: 150, fontWeight: 800, fontFamily: BRAND.mono,
                color: isZero ? BRAND.gold : BRAND.accent, lineHeight: 1,
              }}>{n}<span style={{ fontSize: 60 }}>{v.unit}</span></div>
              <div style={{ fontSize: TYPO.body, color: BRAND.text, marginTop: 28 }}>{v.sub}</div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
