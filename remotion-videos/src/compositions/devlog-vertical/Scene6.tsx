import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND, CONTENT, SAFE, SHOTS } from './constants';
import { fadeSlideUp, sceneFadeOut } from './utils';
const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };
/** S6 拆镜头：真实分镜表滚动 */
export const Scene6: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const out = sceneFadeOut(frame, durationInFrames);
  // 列表持续向上滚动，滚到末尾停住
  const roll = interpolate(frame, [10, durationInFrames - 30], [0, 1], clamp);
  const step = 62;
  const offset = roll * (SHOTS.length * step - 260);
  return (
    <AbsoluteFill style={{ background: BRAND.bg, opacity: out }}>
      <div style={{
        position: 'absolute', left: SAFE.side, right: SAFE.side, top: 0, bottom: 0,
        display: 'flex', flexDirection: 'column',
      }}>
        <div style={{ marginTop: 40, ...fadeSlideUp(frame, 0, 20) }}>
          <div style={{ fontSize: 52, fontWeight: 700, color: BRAND.text }}>{CONTENT.shotTitle}</div>
          <div style={{ fontSize: 27, color: BRAND.accent, marginTop: 12, fontFamily: BRAND.mono }}>
            {CONTENT.shotSub}
          </div>
        </div>
        <div style={{
          marginTop: 28, flex: 1, overflow: 'hidden', position: 'relative',
          maskImage: 'linear-gradient(180deg, transparent 0%, #000 8%, #000 88%, transparent 100%)',
          WebkitMaskImage: 'linear-gradient(180deg, transparent 0%, #000 8%, #000 88%, transparent 100%)',
        }}>
          <div style={{ position: 'absolute', top: -offset, left: 0, right: 0 }}>
            {SHOTS.map((s, i) => {
              const op = interpolate(
                frame,
                [10 + i * 4, 26 + i * 4, durationInFrames - 40, durationInFrames - 14],
                [0, 1, 1, 0],
                clamp,
              );
              const isKey = i % 2 === 0;
              return (
                <div key={s} style={{
                  display: 'flex', alignItems: 'center', gap: 14, opacity: op,
                  padding: '12px 18px', marginBottom: 8, borderRadius: 12,
                  background: 'rgba(24,23,34,0.82)',
                  border: '1px solid rgba(231,240,249,0.08)',
                }}>
                  <div style={{
                    fontSize: 20, fontFamily: BRAND.mono, color: BRAND.text2, width: 42,
                  }}>
                    {String(i + 1).padStart(2, '0')}
                  </div>
                  <div style={{ flex: 1, fontSize: 26, color: BRAND.text }}>{s}</div>
                  <div style={{
                    fontSize: 18, fontFamily: BRAND.mono, padding: '5px 11px', borderRadius: 8,
                    color: isKey ? BRAND.accent : BRAND.text2,
                    background: isKey ? BRAND.accentDim : 'rgba(231,240,249,0.07)',
                  }}>
                    {isKey ? '重要' : '过场'}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
