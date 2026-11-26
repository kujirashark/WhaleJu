import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND, CONTENT, SAFE, SHOTS_UI } from './constants';
import { fadeSlideUp, pop, sceneFadeOut, WindowCard } from './utils';
/** S4 确认剧本：截图 + "你点头才往下走" */
export const Scene4: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const out = sceneFadeOut(frame, durationInFrames);
  const mark = pop(frame, fps, 16);
  return (
    <AbsoluteFill style={{ background: BRAND.bg, opacity: out }}>
      <div style={{
        position: 'absolute', left: SAFE.side, right: SAFE.side, top: 0, bottom: 0,
        display: 'flex', flexDirection: 'column', justifyContent: 'flex-start', paddingTop: 150,
      }}>
        <div style={{ ...fadeSlideUp(frame, 0, 20) }}>
          <div style={{
            fontSize: 56, fontWeight: 700, color: BRAND.text,
            lineHeight: 1.24, whiteSpace: 'pre-line',
          }}>
            {CONTENT.confirmTitle}
          </div>
        </div>
        <div style={{ marginTop: 28, ...fadeSlideUp(frame, 14, 22) }}>
          <WindowCard src={SHOTS_UI.confirm} width={960} />
        </div>
        <div style={{
          marginTop: 30, display: 'flex', alignItems: 'center', gap: 14,
          ...fadeSlideUp(frame, 24, 20),
        }}>
          <div style={{
            transform: `scale(${mark})`, width: 42, height: 42, borderRadius: 12,
            background: BRAND.accent, display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#04121c" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 6 9 17l-5-5" />
            </svg>
          </div>
          <div style={{ fontSize: 30, color: BRAND.text }}>{CONTENT.confirmSub}</div>
          <div style={{
            marginLeft: 'auto', fontSize: 22, color: BRAND.ok, fontFamily: BRAND.mono,
            border: `1px solid ${BRAND.ok}66`, borderRadius: 999, padding: '6px 14px',
          }}>
            已确认
          </div>
        </div>
        <div style={{
          marginTop: 28, fontSize: 25, color: BRAND.text2, lineHeight: 1.8,
          ...fadeSlideUp(frame, 44, 20),
        }}>
          剧本随时可以重写。改完再确认，
          <br />
          不满意就重来，额度按成功镜头算。
        </div>
      </div>
    </AbsoluteFill>
  );
};
