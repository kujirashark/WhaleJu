import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import { BRAND, CONTENT, SAFE, SHOTS_UI } from './constants';
import { fadeSlideUp, sceneFadeOut, staggerIn, WindowCard } from './utils';
/** S3 写剧本：真实截图 + 三集标题 */
export const Scene3: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const out = sceneFadeOut(frame, durationInFrames);
  return (
    <AbsoluteFill style={{ background: BRAND.bg, opacity: out }}>
      <div style={{
        position: 'absolute', left: SAFE.side, right: SAFE.side, top: 0, bottom: 0,
        display: 'flex', flexDirection: 'column', justifyContent: 'flex-start', paddingTop: 110,
      }}>
        <div style={{ ...fadeSlideUp(frame, 0, 20) }}>
          <div style={{ fontSize: 52, fontWeight: 700, color: BRAND.text }}>{CONTENT.scriptTitle}</div>
          <div style={{ fontSize: 27, color: BRAND.accent, marginTop: 12, fontFamily: BRAND.mono }}>
            {CONTENT.scriptSub}
          </div>
        </div>
        <div style={{ marginTop: 30, ...fadeSlideUp(frame, 18, 22) }}>
          <WindowCard src={SHOTS_UI.script} width={960} />
        </div>
        <div style={{ marginTop: 28, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {CONTENT.episodes.map((e, i) => (
            <div key={e.t} style={{
              display: 'flex', alignItems: 'center', gap: 16,
              background: 'rgba(24,23,34,0.85)', border: '1px solid rgba(231,240,249,0.1)',
              borderRadius: 12, padding: '14px 20px', ...staggerIn(frame, i, 14, 40),
            }}>
              <div style={{
                fontSize: 20, color: BRAND.accent, fontFamily: BRAND.mono,
                background: BRAND.accentDim, padding: '6px 12px', borderRadius: 8,
              }}>
                EP.0{i + 1}
              </div>
              <div style={{ fontSize: 30, color: BRAND.text, fontWeight: 700, width: 130 }}>
                {e.t}
              </div>
              <div style={{ fontSize: 27, color: BRAND.text2 }}>{e.d}</div>
            </div>
          ))}
        </div>
        {/* 真实剧本里的标签 */}
        <div style={{
          marginTop: 26, display: 'flex', flexWrap: 'wrap', gap: 10,
          ...fadeSlideUp(frame, 92, 20),
        }}>
          {['童年', '亲情', '追梦', '催泪', '成长', '年代'].map((t) => (
            <div key={t} style={{
              fontSize: 22, color: BRAND.text2, fontFamily: BRAND.mono,
              border: '1px solid rgba(231,240,249,0.16)', borderRadius: 999,
              padding: '7px 15px',
            }}>
              #{t}
            </div>
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};
