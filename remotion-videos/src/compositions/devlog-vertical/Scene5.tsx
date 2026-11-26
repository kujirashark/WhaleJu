import React from 'react';
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND, CONTENT, ROLES, SAFE } from './constants';
import { fadeSlideUp, sceneFadeOut, staggerIn } from './utils';
const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };
const AGE = ['角色 1', '角色 2', '角色 3', '角色 4', '角色 5'];
/** S5 定角色：5 张真实定妆图横排 */
export const Scene5: React.FC = () => {
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
          <div style={{ fontSize: 52, fontWeight: 700, color: BRAND.text }}>{CONTENT.roleTitle}</div>
          <div style={{ fontSize: 27, color: BRAND.accent, marginTop: 12, fontFamily: BRAND.mono }}>
            {CONTENT.roleSub}
          </div>
        </div>
        <div style={{
          marginTop: 36, display: 'flex', gap: 14, justifyContent: 'center',
        }}>
          {ROLES.map((r, i) => {
            const start = 22 + i * 12;
            const op = interpolate(frame, [start, start + 20], [0, 1], clamp);
            const y = interpolate(frame, [start, start + 26], [40, 0], clamp);
            return (
              <div key={r} style={{ opacity: op, transform: `translateY(${y}px)`, flex: 1 }}>
                <div style={{
                  borderRadius: 14, overflow: 'hidden', border: '1px solid rgba(231,240,249,0.14)',
                  background: '#0b111b', aspectRatio: '2 / 3',
                }}>
                  <Img
                    src={staticFile(r)}
                    style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
                  />
                </div>
                <div style={{
                  marginTop: 12, textAlign: 'center', fontSize: 20,
                  color: BRAND.text2, fontFamily: BRAND.mono,
                }}>
                  {AGE[i]}
                </div>
              </div>
            );
          })}
        </div>
        <div style={{
          marginTop: 34, display: 'flex', flexDirection: 'column', gap: 10,
        }}>
          {['8 岁', '22 岁', '35 岁', '60 岁', '100 岁'].map((t, i) => (
            <div key={t} style={{
              display: 'flex', alignItems: 'center', gap: 14, ...staggerIn(frame, i, 12, 92),
            }}>
              <div style={{ width: 96, fontSize: 26, color: BRAND.text, fontFamily: BRAND.mono }}>
                {t}
              </div>
              <div style={{
                flex: 1, height: 8, borderRadius: 8, background: 'rgba(231,240,249,0.1)',
              }}>
                <div style={{
                  height: 8, borderRadius: 8, width: `${20 + i * 20}%`, background: BRAND.accent,
                }} />
              </div>
              <div style={{ fontSize: 20, color: BRAND.text2 }}>已锁定</div>
            </div>
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};
