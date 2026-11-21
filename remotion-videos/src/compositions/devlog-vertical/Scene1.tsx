import React from 'react';
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND, CONTENT, SHOTS_UI } from './constants';
import { fadeSlideUp, pop, sceneFadeOut, typewriter, WhaleMark } from './utils';
const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };
/** S1 钩子：真实界面做背景虚化，主标题压上去 */
export const Scene1: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const out = sceneFadeOut(frame, durationInFrames);
  const mark = pop(frame, fps, 0);
  const zoom = interpolate(frame, [0, durationInFrames], [1.12, 1.02], clamp);
  const drift = interpolate(frame, [0, durationInFrames], [0, -26], clamp);
  return (
    <AbsoluteFill style={{ background: BRAND.bg, opacity: out, overflow: 'hidden' }}>
      {/* 背景：真实界面截图放大虚化（保留可辨识细节，压暗保证文字可读） */}
      <div style={{
        position: 'absolute', inset: -60, opacity: 0.85, filter: 'blur(9px) brightness(0.72)',
        transform: `scale(${zoom}) translateY(${drift}px)`,
      }}>
        <Img src={staticFile(SHOTS_UI.roles)} style={{ width: '100%', display: 'block' }} />
      </div>
      <div style={{
        position: 'absolute', inset: 0,
        background: `linear-gradient(180deg, ${BRAND.bg}E6 0%, ${BRAND.bg}F2 40%, ${BRAND.bg} 100%)`,
      }} />
      <div style={{
        position: 'absolute', left: 60, right: 60, top: 0, bottom: 0,
        display: 'flex', flexDirection: 'column', justifyContent: 'flex-start',
        paddingTop: 150,
      }}>
        <div style={{ transform: `scale(${mark})`, display: 'flex', alignItems: 'center', gap: 14, marginBottom: 30 }}>
          <WhaleMark size={46} />
          <div style={{ fontSize: 30, fontWeight: 700, color: BRAND.text }}>{CONTENT.brand}</div>
          <div style={{
            fontSize: 19, color: BRAND.accent, fontFamily: BRAND.mono,
            border: `1px solid ${BRAND.accent}55`, borderRadius: 999, padding: '5px 13px',
          }}>
            {CONTENT.dayTag}
          </div>
        </div>
        <div style={{
          fontSize: 86, fontWeight: 700, color: BRAND.text, lineHeight: 1.16,
          whiteSpace: 'pre-line', letterSpacing: '0.01em', ...fadeSlideUp(frame, 18, 22),
        }}>
          {CONTENT.hook}
        </div>
        <div style={{
          fontSize: 36, color: BRAND.accent, marginTop: 30, fontFamily: BRAND.mono,
          ...fadeSlideUp(frame, 44, 22),
        }}>
          {CONTENT.hookSub}
        </div>
        <div style={{
          marginTop: 46, display: 'flex', gap: 10, ...fadeSlideUp(frame, 70, 22),
        }}>
          {['写剧本', '定角色', '拆镜头', '出画面'].map((t, i) => (
            <div key={t} style={{
              fontSize: 24, color: BRAND.text2, padding: '10px 18px',
              border: `1px solid rgba(231,240,249,0.18)`, borderRadius: 10,
              background: 'rgba(24,23,34,0.72)', opacity: interpolate(frame, [70 + i * 8, 88 + i * 8], [0, 1], clamp),
            }}>
              {t}
            </div>
          ))}
        </div>
        <div style={{
          marginTop: 52, fontSize: 22, color: BRAND.text2, fontFamily: BRAND.mono,
          lineHeight: 1.9, opacity: interpolate(frame, [92, 112], [0, 1], clamp),
        }}>
          {'> 本地引擎已连接'}
          <br />
          {'> 全部模型调用都留日志'}
        </div>
      </div>
    </AbsoluteFill>
  );
};
