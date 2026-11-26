import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND, CONTENT, SAFE } from './constants';
import { cursorOpacity, fadeSlideUp, sceneFadeOut, typewriter } from './utils';
/** S2 一句话起步：首页输入框的打字机 */
export const Scene2: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const out = sceneFadeOut(frame, durationInFrames);
  const text = typewriter(frame, CONTENT.idea, 1.7, 14);
  return (
    <AbsoluteFill style={{ background: BRAND.bg, opacity: out }}>
      <div style={{
        position: 'absolute', left: SAFE.side, right: SAFE.side, top: 0, bottom: 0,
        display: 'flex', flexDirection: 'column', justifyContent: 'flex-start',
        paddingTop: 150,
      }}>
        <div style={{
          fontSize: 22, color: BRAND.accent, fontFamily: BRAND.mono,
          letterSpacing: '0.14em', ...fadeSlideUp(frame, 0, 18),
        }}>
          {CONTENT.ideaLabel.toUpperCase()}
        </div>
        {/* 输入框 */}
        <div style={{
          marginTop: 26, borderRadius: 20, border: `1px solid ${BRAND.accent}66`,
          background: 'rgba(24,23,34,0.9)', padding: '30px 32px',
          boxShadow: `0 0 0 1px ${BRAND.accentDim}, 0 20px 50px rgba(0,0,0,0.45)`,
          ...fadeSlideUp(frame, 8, 20),
        }}>
          <div style={{
            fontSize: 38, color: BRAND.text, lineHeight: 1.5, minHeight: 58,
          }}>
            {text}
            <span style={{
              display: 'inline-block', width: 3, height: 36, marginLeft: 6,
              background: BRAND.accent, verticalAlign: -6, opacity: cursorOpacity(frame),
            }} />
          </div>
        </div>
        {/* 提示：这是本地跑的 */}
        <div style={{
          marginTop: 34, display: 'flex', alignItems: 'center', gap: 12,
          ...fadeSlideUp(frame, 60, 20),
        }}>
          <span style={{
            width: 10, height: 10, borderRadius: 10, background: BRAND.ok,
            boxShadow: `0 0 12px ${BRAND.ok}`,
          }} />
          <div style={{ fontSize: 28, color: BRAND.text2 }}>
            不用注册，不联网也能先跑起来
          </div>
        </div>
        <div style={{
          marginTop: 46, fontSize: 24, color: BRAND.text2, fontFamily: BRAND.mono,
          lineHeight: 1.8, ...fadeSlideUp(frame, 84, 20),
        }}>
          {'> 本地引擎已连接'}
          <br />
          {'> 文本模型：sensenova-6.8-flash-lite'}
          <br />
          {'> 正在生成剧本…'}
        </div>
        {/* 生成进度（真实状态：3 集） */}
        <div style={{
          marginTop: 34, ...fadeSlideUp(frame, 104, 20),
        }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', fontSize: 22,
            color: BRAND.text2, fontFamily: BRAND.mono, marginBottom: 10,
          }}>
            <span>第 1 集 / 共 3 集</span>
            <span style={{ color: BRAND.accent }}>生成中</span>
          </div>
          <div style={{
            height: 10, borderRadius: 10, background: 'rgba(231,240,249,0.1)', overflow: 'hidden',
          }}>
            <div style={{
              height: 10, borderRadius: 10, width: `${Math.min(100, ((frame - 104) / 50) * 100)}%`,
              background: `linear-gradient(90deg, ${BRAND.accent}, ${BRAND.ok})`,
            }} />
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
