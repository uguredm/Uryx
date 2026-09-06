import { useEffect, useRef } from 'react';
import { Mic, MicOff } from 'lucide-react';

import { readHudGlow } from '@/lib/theme';
import { useI18n } from '@/lib/i18n';
import { useSettingsStore } from '@/stores/settingsStore';

export type UryxCoreState =
  'ready' | 'offline' | 'listening' | 'transcribing' | 'thinking' | 'speaking' | 'error';

interface Particle {
  angle: number;
  radius: number;
  speed: number;
  size: number;
  phase: number;
}

const STATIC_COLORS: Record<UryxCoreState, [number, number, number]> = {
  ready: [0, 212, 192],
  offline: [91, 112, 110],
  listening: [35, 225, 145],
  transcribing: [255, 153, 0],
  thinking: [255, 102, 0],
  speaking: [53, 174, 255],
  error: [240, 65, 93],
};

export function UryxCoreCanvas({
  state,
  level,
  onActivate,
}: {
  state: UryxCoreState;
  level: number;
  onActivate: () => void;
}): JSX.Element {
  const { t } = useI18n();
  const accentTheme = useSettingsStore((store) => store.settings.accentTheme);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const particlesRef = useRef<Particle[]>([]);
  const levelRef = useRef(level);

  useEffect(() => {
    levelRef.current = level;
  }, [level]);

  if (particlesRef.current.length === 0) {
    particlesRef.current = Array.from({ length: 120 }, (_, index) => ({
      angle: (index / 120) * Math.PI * 2 + Math.sin(index * 17.1) * 0.16,
      radius: 0.19 + ((index * 37) % 100) / 310,
      speed: 0.055 + ((index * 19) % 23) / 210,
      size: 0.55 + ((index * 13) % 8) / 7,
      phase: index * 0.73,
    }));
  }

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext('2d');
    if (!context) return;

    let frame = 0;
    let animationId = 0;
    let width = 0;
    let height = 0;
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const resize = (): void => {
      const bounds = canvas.getBoundingClientRect();
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = Math.max(1, bounds.width);
      height = Math.max(1, bounds.height);
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
    };

    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    resize();

    const drawArcSegments = (
      cx: number,
      cy: number,
      radius: number,
      rotation: number,
      count: number,
      span: number,
      color: string,
      lineWidth: number,
    ): void => {
      context.strokeStyle = color;
      context.lineWidth = lineWidth;
      context.lineCap = 'round';
      for (let index = 0; index < count; index += 1) {
        const start = rotation + (index / count) * Math.PI * 2;
        context.beginPath();
        context.arc(cx, cy, radius, start, start + span);
        context.stroke();
      }
    };

    const render = (): void => {
      frame += reduceMotion ? 0 : 1;
      const time = frame / 60;
      const accent = readHudGlow();
      const [red, green, blue] =
        state === 'ready' || state === 'listening' ? accent : STATIC_COLORS[state];
      const color = (alpha: number): string => `rgba(${red}, ${green}, ${blue}, ${alpha})`;
      const cx = width / 2;
      const cy = height / 2;
      const base = Math.min(width, height);
      const activity = Math.min(1, Math.max(0, levelRef.current));
      const stateEnergy = state === 'speaking' ? 0.9 : state === 'listening' ? 0.65 : 0.25;
      const energy = Math.max(stateEnergy, activity);

      context.clearRect(0, 0, width, height);
      context.save();
      context.globalCompositeOperation = 'lighter';

      const pulse =
        1 + Math.sin(time * (state === 'speaking' ? 7 : 2.4)) * (0.008 + energy * 0.018);
      const glowRadius = base * (0.21 + energy * 0.012) * pulse;
      const glow = context.createRadialGradient(cx, cy, 0, cx, cy, glowRadius);
      glow.addColorStop(0, color(0.08 + energy * 0.04));
      glow.addColorStop(0.5, color(0.035));
      glow.addColorStop(1, color(0));
      context.fillStyle = glow;
      context.beginPath();
      context.arc(cx, cy, glowRadius, 0, Math.PI * 2);
      context.fill();

      for (const particle of particlesRef.current) {
        const orbit = particle.radius * base * (1 + Math.sin(time * 1.4 + particle.phase) * 0.035);
        const angle = particle.angle + time * particle.speed * (0.7 + energy * 2.4);
        const push = 1 + activity * 0.12 * Math.sin(particle.phase + time * 8);
        const x = cx + Math.cos(angle) * orbit * push;
        const y = cy + Math.sin(angle) * orbit * push;
        const alpha = 0.16 + (1 - particle.radius) * 0.28 + energy * 0.16;
        context.fillStyle = color(alpha);
        context.beginPath();
        context.arc(x, y, particle.size + energy * 0.45, 0, Math.PI * 2);
        context.fill();
      }

      context.strokeStyle = color(0.13);
      context.lineWidth = 1;
      for (const ratio of [0.19, 0.25, 0.33, 0.41]) {
        context.beginPath();
        context.arc(cx, cy, base * ratio * pulse, 0, Math.PI * 2);
        context.stroke();
      }

      drawArcSegments(cx, cy, base * 0.42, time * 0.15, 18, 0.085, color(0.42), 1);
      drawArcSegments(cx, cy, base * 0.355, -time * 0.28, 12, 0.16, color(0.6), 2);
      drawArcSegments(cx, cy, base * 0.285, time * 0.45, 8, 0.25, color(0.74), 2.5);

      const coreRadius = base * (0.14 + activity * 0.008) * pulse;
      const [coreR, coreG, coreB] = getComputedStyle(document.documentElement)
        .getPropertyValue('--hud-core-fill')
        .split(',')
        .map((part) => Number(part.trim()));
      context.fillStyle = Number.isFinite(coreR)
        ? `rgba(${coreR}, ${coreG}, ${coreB}, 0.94)`
        : 'rgba(2, 12, 12, 0.94)';
      context.shadowColor = color(0.9);
      context.shadowBlur = 22 + energy * 24;
      context.beginPath();
      context.arc(cx, cy, coreRadius, 0, Math.PI * 2);
      context.fill();
      context.shadowBlur = 0;
      context.strokeStyle = color(0.85);
      context.lineWidth = 1.5;
      context.stroke();

      context.restore();
      animationId = window.requestAnimationFrame(render);
    };

    animationId = window.requestAnimationFrame(render);
    return () => {
      window.cancelAnimationFrame(animationId);
      observer.disconnect();
    };
  }, [state, accentTheme]);

  const disabled = state === 'offline';
  return (
    <button
      type="button"
      className="uryx-hud-core"
      data-state={state}
      onClick={onActivate}
      disabled={disabled}
      aria-label={state === 'listening' ? t('hud.core.listenStop') : t('hud.core.listenStart')}
      title={state === 'listening' ? t('hud.core.listenStop') : t('hud.core.listenStart')}
    >
      <canvas ref={canvasRef} className="uryx-hud-core__canvas" aria-hidden />
      <span className="uryx-hud-core__action">
        {disabled ? <MicOff size={26} /> : <Mic size={26} />}
      </span>
    </button>
  );
}
