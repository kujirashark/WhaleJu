import React from 'react';
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND, CONTENT, FRAMES, SAFE } from './constants';
import { fadeSlideUp, pop, pulse, sceneFadeOut, WhaleMark } from './utils';
const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };
/** S9 收尾：真实画面做背景条 + 品牌 + 关注引导 + AI 声明 */
export const Scene9: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const out = sceneFadeOut(frame, durationInFrames);
  const mark = pop(frame, fps, 10);
  const glow = pulse(frame, 0.22, 0.12);
  return (
    <AbsoluteFill style={{ background: BRAND.bg, opacity: out, overflow: 'hidden' }}>
      {/* 底部一排真实画面做氛围 */}
      <div style={{
        position: 'absolute', left: 0, right: 0, bottom: 0, height: 560,
        display: 'flex', gap: 6, opacity: 0.6,
      }}>
        {FRAMES.slice(0, 6).map((f) => (
          <Img
            key={f}
            src={staticFile(f)}
            style={{ flex: 1, height: '100%', objectFit: 'cover', display: 'block' }}
          />
        ))}
      </div>
      <div style={{
        position: 'absolute', inset: 0,
        background: `linear-gradient(180deg, ${BRAND.bg} 40%, ${BRAND.bg}D0 62%, ${BRAND.bg}55 100%)`,
      }} />
      <div style={{
        position: 'absolute', left: SAFE.side, right: SAFE.side, top: 0, bottom: 0,
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'flex-start', paddingTop: 230, textAlign: 'center',
      }}>
        <div style={{
          transform: `scale(${mark})`, position: 'relative',
        }}>
          <div style={{
            position: 'absolute', inset: -70, borderRadius: '50%',
            background: `radial-gradient(circle, ${BRAND.accent}33 0%, transparent 68%)`,
            opacity: glow,
          }} />
          <WhaleMark size={110} />
        </div>
        <div style={{
          fontSize: 62, fontWeight: 700, color: BRAND.text, marginTop: 26,
          ...fadeSlideUp(frame, 22, 20),
        }}>
          {CONTENT.brand}
        </div>
        <div style={{
          fontSize: 40, color: BRAND.accent, marginTop: 22, fontWeight: 700,
          ...fadeSlideUp(frame, 36, 20),
        }}>
          {CONTENT.ctaTitle}
        </div>
        <div style={{
          fontSize: 30, color: BRAND.text2, marginTop: 14,
          ...fadeSlideUp(frame, 46, 20),
        }}>
          {CONTENT.ctaSub}
        </div>
        <div style={{
          marginTop: 40, display: 'flex', alignItems: 'center', gap: 12,
          border: `1px solid ${BRAND.accent}55`, borderRadius: 999,
          padding: '14px 28px', background: 'rgba(0,212,255,0.08)',
          ...fadeSlideUp(frame, 54, 20),
        }}>
          <span style={{ fontSize: 26, color: BRAND.text }}>评论区聊聊</span>
          <span style={{ fontSize: 26, color: BRAND.accent, fontFamily: BRAND.mono }}>
            你最想让 AI 写什么故事？
          </span>
        </div>
        {/* 合规说明：常驻角标已覆盖 AI 标识，这里只补一句更完整的声明 */}
        <div style={{
          position: 'absolute', bottom: 590, left: 0, right: 0,
          fontSize: 21, color: BRAND.text2, fontFamily: BRAND.mono,
          opacity: interpolate(frame, [70, 88], [0, 1], clamp),
        }}>
          {CONTENT.aiBadge} · 素材与调用均在本机完成
        </div>
      </div>
    </AbsoluteFill>
  );
};
