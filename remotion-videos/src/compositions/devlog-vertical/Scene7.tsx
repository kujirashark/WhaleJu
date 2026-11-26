import React from 'react';
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND, CONTENT, FRAMES, SAFE } from './constants';
import { fadeSlideUp, sceneFadeOut } from './utils';
const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };
/** S7 生成画面：12 张真实生成画面逐个亮起 */
export const Scene7: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const out = sceneFadeOut(frame, durationInFrames);
  const done = Math.min(12, Math.floor(Math.max(0, frame - 18) / 12) + 1);
  return (
    <AbsoluteFill style={{ background: BRAND.bg, opacity: out }}>
      <div style={{
        position: 'absolute', left: SAFE.side, right: SAFE.side, top: 0, bottom: 0,
        display: 'flex', flexDirection: 'column',
      }}>
        <div style={{ marginTop: 40, ...fadeSlideUp(frame, 0, 20) }}>
          <div style={{ fontSize: 52, fontWeight: 700, color: BRAND.text }}>{CONTENT.frameTitle}</div>
          <div style={{
            fontSize: 27, color: BRAND.accent, marginTop: 12, fontFamily: BRAND.mono,
            display: 'flex', alignItems: 'center', gap: 14,
          }}>
            <span>{CONTENT.frameSub}</span>
            <span style={{ color: BRAND.ok }}>{done} / 12</span>
          </div>
        </div>
        {/* 4 × 3 网格：真实画面依次点亮（竖图完整显示，不裁脸） */}
        <div style={{
          marginTop: 30, display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 10,
        }}>
          {FRAMES.map((f, i) => {
            const start = 18 + i * 12;
            const op = interpolate(frame, [start, start + 14], [0, 1], clamp);
            const s = interpolate(frame, [start, start + 20], [0.86, 1], clamp);
            const isNew = i === done - 1;
            return (
              <div key={f} style={{
                position: 'relative', opacity: op, transform: `scale(${s})`,
                borderRadius: 10, overflow: 'hidden',
                border: isNew ? `2px solid ${BRAND.accent}` : '1px solid rgba(231,240,249,0.12)',
                background: '#0b111b', aspectRatio: '9 / 16',
              }}>
                <Img
                  src={staticFile(f)}
                  style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
                />
                <div style={{
                  position: 'absolute', left: 5, bottom: 5, fontSize: 14,
                  fontFamily: BRAND.mono, color: BRAND.text,
                  background: 'rgba(13,20,32,0.72)', padding: '2px 6px', borderRadius: 5,
                }}>
                  {String(i + 1).padStart(2, '0')}
                </div>
              </div>
            );
          })}
        </div>
        <div style={{
          marginTop: 26, fontSize: 24, color: BRAND.text2, fontFamily: BRAND.mono,
          ...fadeSlideUp(frame, 140, 20),
        }}>
          12 个镜头 · 每镜 1.5 额度 · 失败不计费
        </div>
      </div>
    </AbsoluteFill>
  );
};
