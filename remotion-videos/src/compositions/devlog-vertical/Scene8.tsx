import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND, CONTENT, SAFE } from './constants';
import { fadeSlideUp, sceneFadeOut, staggerIn } from './utils';
/** S8 技术细节：不是黑盒，三张要点卡 */
export const Scene8: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const out = sceneFadeOut(frame, durationInFrames);
  return (
    <AbsoluteFill style={{ background: BRAND.bg, opacity: out }}>
      <div style={{
        position: 'absolute', left: SAFE.side, right: SAFE.side, top: 0, bottom: 0,
        display: 'flex', flexDirection: 'column', justifyContent: 'center',
      }}>
        <div style={{ ...fadeSlideUp(frame, 0, 20) }}>
          <div style={{ fontSize: 54, fontWeight: 700, color: BRAND.text }}>{CONTENT.techTitle}</div>
          <div style={{ fontSize: 27, color: BRAND.accent, marginTop: 12, fontFamily: BRAND.mono }}>
            每次调用都有日志，出了问题看得到
          </div>
        </div>
        <div style={{ marginTop: 36, display: 'flex', flexDirection: 'column', gap: 18 }}>
          {CONTENT.techPoints.map((p, i) => (
            <div key={p.t} style={{
              display: 'flex', alignItems: 'center', gap: 20,
              background: 'rgba(24,23,34,0.88)',
              border: '1px solid rgba(231,240,249,0.1)', borderRadius: 16,
              padding: '24px 26px', ...staggerIn(frame, i, 20, 30),
            }}>
              <div style={{
                width: 54, height: 54, borderRadius: 14, background: BRAND.accentDim,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 26, color: BRAND.accent, fontFamily: BRAND.mono, fontWeight: 700,
              }}>
                {i + 1}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 32, fontWeight: 700, color: BRAND.text }}>{p.t}</div>
                <div style={{ fontSize: 24, color: BRAND.text2, marginTop: 6 }}>{p.d}</div>
              </div>
            </div>
          ))}
        </div>
        {/* 真实调用日志样式 */}
        <div style={{
          marginTop: 30, borderRadius: 14, background: '#0b111b',
          border: '1px solid rgba(231,240,249,0.1)', padding: '18px 22px',
          fontFamily: BRAND.mono, fontSize: 20, color: BRAND.text2,
          lineHeight: 1.85, ...fadeSlideUp(frame, 100, 20),
        }}>
          <div><span style={{ color: BRAND.ok }}>200</span> POST /images/generations · 2481ms</div>
          <div><span style={{ color: BRAND.warn }}>429</span> POST /images/generations · 自动重试 1/3</div>
          <div><span style={{ color: BRAND.ok }}>200</span> GET /assets/... · 已落地本机</div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
