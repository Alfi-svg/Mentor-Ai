"use client";

import React, { useEffect, useRef } from "react";

export type OrbState = "idle" | "listening" | "thinking" | "speaking" | "error";

interface CopilotVoiceOrbProps {
  state: OrbState;
  size?: number;
  className?: string;
  onClick?: () => void;
}

export function CopilotVoiceOrb({
  state,
  size = 180,
  className = "",
  onClick,
}: CopilotVoiceOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animationFrameRef = useRef<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let step = 0;
    const prefersReducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const render = () => {
      ctx.clearRect(0, 0, size, size);
      const centerX = size / 2;
      const centerY = size / 2;
      const baseRadius = size * 0.28;

      step += prefersReducedMotion ? 0.01 : 0.035;

      // Color scheme based on assistant state
      let primaryGlow = "rgba(99, 102, 241, 0.45)"; // Indigo
      let secondaryGlow = "rgba(168, 85, 247, 0.35)"; // Purple
      let coreColor = "rgba(129, 140, 248, 0.9)"; // Bright Indigo

      if (state === "listening") {
        primaryGlow = "rgba(236, 72, 153, 0.55)"; // Pink / Magenta
        secondaryGlow = "rgba(59, 130, 246, 0.5)"; // Blue
        coreColor = "rgba(244, 114, 182, 0.95)";
      } else if (state === "thinking") {
        primaryGlow = "rgba(245, 158, 11, 0.55)"; // Amber
        secondaryGlow = "rgba(14, 165, 233, 0.45)"; // Sky
        coreColor = "rgba(251, 191, 36, 0.95)";
      } else if (state === "speaking") {
        primaryGlow = "rgba(16, 185, 129, 0.55)"; // Emerald
        secondaryGlow = "rgba(6, 182, 212, 0.5)"; // Cyan
        coreColor = "rgba(52, 211, 153, 0.95)";
      } else if (state === "error") {
        primaryGlow = "rgba(239, 68, 68, 0.55)"; // Rose
        secondaryGlow = "rgba(249, 115, 22, 0.45)"; // Orange
        coreColor = "rgba(248, 113, 113, 0.95)";
      }

      // 1. Ambient Outer Halo
      const outerPulse = Math.sin(step * 0.8) * 8;
      const outerGrad = ctx.createRadialGradient(
        centerX,
        centerY,
        baseRadius * 0.5,
        centerX,
        centerY,
        baseRadius * 1.6 + outerPulse
      );
      outerGrad.addColorStop(0, primaryGlow);
      outerGrad.addColorStop(0.6, secondaryGlow);
      outerGrad.addColorStop(1, "rgba(0, 0, 0, 0)");

      ctx.beginPath();
      ctx.arc(centerX, centerY, baseRadius * 1.6 + outerPulse, 0, Math.PI * 2);
      ctx.fillStyle = outerGrad;
      ctx.fill();

      // 2. Harmonic Wave Rings (Siri / JARVIS Energy Rings)
      const numRings = state === "speaking" ? 5 : 3;
      for (let i = 0; i < numRings; i++) {
        const ringOffset = i * (Math.PI / 2.5);
        const radiusMod =
          state === "speaking"
            ? Math.sin(step * 2.2 + ringOffset) * (size * 0.08)
            : state === "listening"
            ? Math.sin(step * 1.5 + ringOffset) * (size * 0.05)
            : Math.sin(step * 0.9 + ringOffset) * (size * 0.025);

        const currentRadius = Math.max(10, baseRadius + radiusMod);

        ctx.save();
        ctx.beginPath();
        ctx.ellipse(
          centerX,
          centerY,
          currentRadius,
          currentRadius * (0.85 + Math.cos(step + i) * 0.15),
          step * 0.4 + i,
          0,
          Math.PI * 2
        );
        ctx.strokeStyle = state === "speaking" ? secondaryGlow : primaryGlow;
        ctx.lineWidth = 1.8;
        ctx.shadowBlur = 10;
        ctx.shadowColor = coreColor;
        ctx.stroke();
        ctx.restore();
      }

      // 3. Central Core Glowing Orb
      const corePulse = Math.sin(step * 1.4) * 4;
      const coreGrad = ctx.createRadialGradient(
        centerX - baseRadius * 0.2,
        centerY - baseRadius * 0.2,
        baseRadius * 0.1,
        centerX,
        centerY,
        baseRadius * 0.75 + corePulse
      );
      coreGrad.addColorStop(0, "#ffffff");
      coreGrad.addColorStop(0.4, coreColor);
      coreGrad.addColorStop(0.85, primaryGlow);
      coreGrad.addColorStop(1, "rgba(0, 0, 0, 0)");

      ctx.beginPath();
      ctx.arc(centerX, centerY, baseRadius * 0.75 + corePulse, 0, Math.PI * 2);
      ctx.fillStyle = coreGrad;
      ctx.shadowBlur = 20;
      ctx.shadowColor = coreColor;
      ctx.fill();

      animationFrameRef.current = requestAnimationFrame(render);
    };

    render();

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [state, size]);

  return (
    <div
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      className={`relative inline-flex items-center justify-center cursor-pointer transition-transform hover:scale-105 active:scale-95 focus:outline-none ${className}`}
      style={{ width: size, height: size }}
      aria-label={`Mentor AI voice visualizer in ${state} mode`}
    >
      <canvas
        ref={canvasRef}
        width={size}
        height={size}
        className="pointer-events-none"
      />
    </div>
  );
}
