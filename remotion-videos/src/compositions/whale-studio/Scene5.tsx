import React from 'react';
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig, interpolate } from 'remotion';
import { BRAND, TYPO } from './constants';
import { fadeSlideUp, sceneFadeOut, Tag, pop } from './utils';
const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };
const AGES = [
  { img: 'child.jpg', label: '八岁' },
  { img: 'teen.jpg', label: '十八岁' },
  { img: 'adult.jpg', label: '二十八岁' },
  { img: 'mid.jpg', label: '四十五岁' },
  { img: 'old.jpg', label: '七十岁' },
];
export const Scene5: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const out = sceneFadeOut(frame, durationInFrames);
  const caption = fadeSlideUp(frame, 100, 24);
  return (
    <AbsoluteFill style={{ background: BRAND.bg, opacity: out, padding: '80px 90px', justifyContent: 'center' }}>
      <div style={{ marginBottom: 40 }}><Tag>角色一致性</Tag></div>
      <div style={{ display: 'flex', gap: 22, justifyContent: 'center' }}>
        {AGES.map((a, i) => {
          const p = pop(frame, fps, 8 + i * 15);
          const badge = interpolate(frame, [20 + i * 15, 35 + i * 15], [0, 1], clamp);
          return (
            <div key={a.img} style={{
              width: 320, opacity: p, transform: `scale(${p})`,
            }}>
              <div style={{
                height: 400, borderRadius: 10, overflow: 'hidden', position: 'relative',
                boxShadow: '0 24px 48px -18px rgba(0,0,0,0.75)',
              }}>
                <Img src={staticFile(`assets/${a.img}`)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                <div style={{
                  position: 'absolute', top: 12, right: 12,
                  background: BRAND.accent, color: BRAND.bg,
                  fontFamily: BRAND.mono, fontSize: 16, fontWeight: 700,
                  padding: '6px 12px', borderRadius: 4,
                  opacity: badge,
                }}>● 已锁定</div>
              </div>
              <div style={{
                marginTop: 14, fontSize: 24, color: BRAND.text,
                fontFamily: BRAND.mono, textAlign: 'center',
              }}>{a.label}</div>
            </div>
          );
        })}
      </div>
      <div style={{
        fontSize: TYPO.h2, color: BRAND.gold, textAlign: 'center',
        marginTop: 46, fontWeight: 700, ...caption,
      }}>一次锁定 · 全剧一致</div>
    </AbsoluteFill>
  );
};
