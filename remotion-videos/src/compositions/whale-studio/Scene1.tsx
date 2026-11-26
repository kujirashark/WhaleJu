import React from 'react';
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig, interpolate } from 'remotion';
import { BRAND, TYPO } from './constants';
import { fadeSlideUp, sceneFadeOut, staggerIn } from './utils';
const PHOTOS = ['child.jpg', 'teen.jpg', 'adult.jpg', 'mid.jpg', 'old.jpg'];
const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };
export const Scene1: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const out = sceneFadeOut(frame, durationInFrames);
  const title = fadeSlideUp(frame, 55, 26);
  return (
    <AbsoluteFill style={{ background: BRAND.bg, opacity: out, overflow: 'hidden' }}>
      {/* 五张剧照层叠瀑布 */}
      {PHOTOS.map((p, i) => {
        const s = staggerIn(frame, i, 12, 0);
        const x = interpolate(frame, [0, 90], [180, 0], clamp);
        return (
          <div key={p} style={{
            position: 'absolute',
            left: 470 + i * 250,
            top: 150 + (i % 2) * 60,
            width: 300, height: 420,
            borderRadius: 12, overflow: 'hidden',
            transform: `translateX(${x}px) rotate(${s.transform ? (i - 2) * 3 : 0}deg)`,
            opacity: s.opacity,
            boxShadow: '0 30px 60px -20px rgba(0,0,0,0.7)',
          }}>
            <Img src={staticFile(`assets/${p}`)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          </div>
        );
      })}
      {/* 暗化渐变保证文字可读 */}
      <div style={{
        position: 'absolute', inset: 0,
        background: `linear-gradient(90deg, ${BRAND.bg} 0%, ${BRAND.bg}ee 38%, transparent 70%)`,
      }} />
      <div style={{
        position: 'absolute', left: 100, top: 0, bottom: 0,
        display: 'flex', flexDirection: 'column', justifyContent: 'center',
        maxWidth: 520, ...title,
      }}>
        <div style={{
          fontFamily: BRAND.mono, fontSize: 20, color: BRAND.accent,
          letterSpacing: '0.2em', marginBottom: 24,
        }}>WHALE AI STUDIO</div>
        <div style={{
          fontSize: TYPO.hero, fontWeight: TYPO.weight, color: BRAND.text,
          lineHeight: 1.28,
        }}>一个想法，<br />能变成一部剧吗？</div>
      </div>
    </AbsoluteFill>
  );
};
