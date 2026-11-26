import React from 'react';
import { Img, interpolate, spring, staticFile } from 'remotion';
import { BRAND, SAFE } from './constants';
type Style = React.CSSProperties;
const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };
/** 淡入 + 上移 */
export const fadeSlideUp = (frame: number, start: number, duration = 20): Style => ({
  opacity: interpolate(frame, [start, start + duration], [0, 1], clamp),
  transform: `translateY(${interpolate(frame, [start, start + duration + 5], [30, 0], clamp)}px)`,
});
/** 错峰列表入场 */
export const staggerIn = (frame: number, index: number, gap = 14, start = 0): Style => ({
  opacity: interpolate(frame, [start + index * gap, start + index * gap + 18], [0, 1], clamp),
  transform: `translateY(${interpolate(frame, [start + index * gap, start + index * gap + 24], [34, 0], clamp)}px)`,
});
/** 打字机（slice，不用逐字 opacity） */
export const typewriter = (frame: number, text: string, speed = 2, start = 0) =>
  text.slice(0, Math.max(0, Math.min(Math.floor((frame - start) / speed), text.length)));
/** 光标：平滑呼吸，不用 Math.round 硬切 */
export const cursorOpacity = (frame: number) =>
  0.35 + 0.65 * (0.5 + 0.5 * Math.sin((frame / 8) * Math.PI));
/** 通用弹入缩放 */
export const pop = (frame: number, fps: number, delay = 0) =>
  spring({
    frame: Math.max(0, frame - delay),
    fps,
    config: { damping: 200, stiffness: 400, mass: 0.7 },
  });
/** 场景出场淡出 */
export const sceneFadeOut = (frame: number, duration: number): number =>
  interpolate(frame, [duration - 14, duration], [1, 0], clamp);
/** 脉冲（正弦） */
export const pulse = (frame: number, base: number, amp: number, period = 45) =>
  base + amp * Math.sin((frame / period) * Math.PI * 2);
/** 鲸鲨鳍形播放标（与产品 logo 同形） */
export const WhaleMark: React.FC<{ size?: number; color?: string }> = ({
  size = 80, color = BRAND.accent,
}) => (
  <svg width={size} height={size * 0.83} viewBox="0 0 48 40" fill="none" aria-hidden>
    <path
      d="M9 27C11 16.5 17 7.5 26 5c3.4-.9 6 .8 6 4.4V27Z"
      fill={color} stroke={color} strokeWidth="2" strokeLinejoin="round"
    />
    <path
      d="M4 33.5q4-3.5 8.5 0t8.5 0t8.5 0t8.5 0t6.5 0"
      stroke={color} strokeWidth="3" strokeLinecap="round"
    />
  </svg>
);
/** 场景容器：竖屏安全区 + 背景 */
export const SceneBase: React.FC<{
  children: React.ReactNode;
  background?: string;
  style?: Style;
}> = ({ children, background = BRAND.bg, style }) => (
  <div style={{
    position: 'absolute', inset: 0, background,
    padding: `${SAFE.top}px ${SAFE.side}px ${SAFE.bottom}px`,
    boxSizing: 'border-box', display: 'flex', flexDirection: 'column',
    overflow: 'hidden', ...style,
  }}>
    {children}
  </div>
);
/** 场景标题 + 副标题（统一排版） */
export const SceneTitle: React.FC<{
  title: string; sub?: string; style?: Style; subStyle?: Style;
}> = ({ title, sub, style, subStyle }) => (
  <>
    <div style={{
      fontSize: 52, fontWeight: 700, color: BRAND.text, lineHeight: 1.22,
      whiteSpace: 'pre-line', letterSpacing: '0.01em', ...style,
    }}>
      {title}
    </div>
    {sub ? (
      <div style={{
        fontSize: TYPO_BODY, color: BRAND.text2, marginTop: 16,
        fontFamily: BRAND.mono, letterSpacing: '0.02em', ...subStyle,
      }}>
        {sub}
      </div>
    ) : null}
  </>
);
const TYPO_BODY = 28;
/** 窗口卡片：把横屏界面截图包成"桌面应用窗口"放进竖屏 */
export const WindowCard: React.FC<{
  src: string; width?: number; radius?: number; style?: Style; children?: React.ReactNode;
}> = ({ src, width = 960, radius = 18, style, children }) => (
  <div style={{
    width, borderRadius: radius, overflow: 'hidden',
    border: `1px solid rgba(231,240,249,0.14)`,
    boxShadow: '0 24px 60px rgba(0,0,0,0.55)',
    background: '#0b111b', ...style,
  }}>
    <div style={{
      height: 34, background: '#121a28', display: 'flex', alignItems: 'center',
      padding: '0 14px', gap: 8,
    }}>
      <span style={{ width: 9, height: 9, borderRadius: 9, background: '#ff5c6c' }} />
      <span style={{ width: 9, height: 9, borderRadius: 9, background: '#e8b96a' }} />
      <span style={{ width: 9, height: 9, borderRadius: 9, background: '#2fe08a' }} />
      <span style={{
        marginLeft: 10, fontSize: 14, color: BRAND.text2, fontFamily: BRAND.mono,
      }}>
        鲸鲨漫剧 · 本地工作台
      </span>
    </div>
    <div style={{ position: 'relative', width: '100%' }}>
      <Img src={staticFile(src)} style={{ width: '100%', display: 'block' }} />
      {children}
    </div>
  </div>
);
/** 全局 AI 生成声明（合规：AI 生成内容需标识） */
export const AiBadge: React.FC<{ opacity?: number }> = ({ opacity = 1 }) => (
  <div style={{
    position: 'absolute', right: SAFE.side, bottom: 96, opacity,
    fontSize: 18, color: BRAND.text2, fontFamily: BRAND.mono,
    border: `1px solid rgba(156,175,197,0.35)`, borderRadius: 999,
    padding: '6px 14px', background: 'rgba(13,20,32,0.72)',
  }}>
    画面由 AI 生成
  </div>
);
/** 顶部品牌条 */
export const TopBar: React.FC<{ note?: string; opacity?: number }> = ({ note, opacity = 1 }) => (
  <div style={{
    display: 'flex', alignItems: 'center', gap: 12, opacity, marginBottom: 26,
  }}>
    <WhaleMark size={34} />
    <div style={{ fontSize: 26, fontWeight: 700, color: BRAND.text }}>鲸鲨漫剧</div>
    {note ? (
      <div style={{
        fontSize: 18, color: BRAND.accent, fontFamily: BRAND.mono,
        border: `1px solid ${BRAND.accent}55`, borderRadius: 999, padding: '4px 12px',
      }}>
        {note}
      </div>
    ) : null}
  </div>
);
