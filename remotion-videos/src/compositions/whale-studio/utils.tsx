import React from 'react';
import { interpolate, spring, useVideoConfig } from 'remotion';
import { BRAND } from './constants';
type Style = React.CSSProperties;
const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };
/** 淡入 + 上移：最通用的入场 */
export const fadeSlideUp = (frame: number, start: number, duration = 20): Style => ({
  opacity: interpolate(frame, [start, start + duration], [0, 1], clamp),
  transform: `translateY(${interpolate(frame, [start, start + duration + 5], [32, 0], clamp)}px)`,
});
/** 列表项错峰入场 */
export const staggerIn = (frame: number, index: number, gap = 16, start = 0): Style => ({
  opacity: interpolate(frame, [start + index * gap, start + index * gap + 20], [0, 1], clamp),
  transform: `translateY(${interpolate(frame, [start + index * gap, start + index * gap + 26], [40, 0], clamp)}px)`,
});
/** 打字机文本（用 slice，不用逐字 opacity） */
export const typewriter = (frame: number, text: string, speed = 2, start = 0) =>
  text.slice(0, Math.max(0, Math.min(Math.floor((frame - start) / speed), text.length)));
/** 数字滚动 */
export const countUp = (frame: number, target: number, start: number, duration: number) =>
  Math.round(target * interpolate(frame, [start, start + duration], [0, 1], clamp));
/** 场景出场淡出（最后 15 帧） */
export const sceneFadeOut = (frame: number, duration: number): number =>
  interpolate(frame, [duration - 16, duration], [1, 0], clamp);
/** 通用 spring 弹入缩放 */
export const pop = (frame: number, fps: number, delay = 0) =>
  spring({
    frame: Math.max(0, frame - delay),
    fps,
    config: { damping: 200, stiffness: 400, mass: 0.7 },
  });
/** 脉冲光环（正弦，用于 CTA/当前节点） */
export const pulse = (frame: number, base: number, amp: number, period = 45) =>
  base + amp * Math.sin((frame / period) * Math.PI * 2);
/** 鲸鲨鳍形播放标（品牌 logo，纯 SVG 路径复用） */
export const WhaleMark: React.FC<{ size?: number; color?: string }> = ({
  size = 80, color = BRAND.accent,
}) => (
  <svg width={size} height={size * 0.83} viewBox="0 0 48 40" fill="none" aria-hidden>
    <path
      d="M9 27C11 16.5 17 7.5 26 5c3.4-.9 6 .8 6 4.4V27Z"
      fill={color}
      stroke={color}
      strokeWidth="2"
      strokeLinejoin="round"
    />
    <path
      d="M4 33.5q4-3.5 8.5 0t8.5 0t8.5 0t8.5 0t6.5 0"
      stroke={color}
      strokeWidth="3"
      strokeLinecap="round"
    />
  </svg>
);
/** 场景通用容器：安全边距 + 背景 */
export const SceneBase: React.FC<{
  children: React.ReactNode;
  background?: string;
  style?: Style;
}> = ({ children, background = BRAND.bg, style }) => (
  <div style={{
    position: 'absolute', inset: 0, background,
    padding: '72px 100px', boxSizing: 'border-box',
    display: 'flex', flexDirection: 'column',
    justifyContent: 'center', overflow: 'hidden', ...style,
  }}>
    {children}
  </div>
);
/** 小标签（等宽青色） */
export const Tag: React.FC<{ children: React.ReactNode; style?: Style }> = ({ children, style }) => (
  <span style={{
    fontFamily: BRAND.mono, fontSize: BRAND_TINY, color: BRAND.accent,
    background: BRAND.accentDim, padding: '6px 14px', borderRadius: 6,
    letterSpacing: '0.06em', ...style,
  }}>{children}</span>
);
const BRAND_TINY = 18;
/** 细网格装饰（极淡，仅背景层） */
export const GridDeco: React.FC<{ opacity?: number }> = ({ opacity = 0.05 }) => (
  <div style={{
    position: 'absolute', inset: 0, pointerEvents: 'none', opacity,
    backgroundImage: `linear-gradient(${BRAND.text2} 1px, transparent 1px), linear-gradient(90deg, ${BRAND.text2} 1px, transparent 1px)`,
    backgroundSize: '60px 60px',
  }} />
);
