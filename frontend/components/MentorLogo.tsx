"use client";

import React from "react";

interface MentorLogoProps {
  size?: "sm" | "md" | "lg" | "xl";
  showWordmark?: boolean;
  subtitle?: string;
  className?: string;
}

export function MentorLogo({
  size = "md",
  showWordmark = true,
  subtitle,
  className = "",
}: MentorLogoProps) {
  // Sizing mappings
  const iconDimensions = {
    sm: "h-7 w-7",
    md: "h-8 w-8",
    lg: "h-10 w-10",
    xl: "h-12 w-12",
  }[size];

  const textSize = {
    sm: "text-sm",
    md: "text-base",
    lg: "text-xl",
    xl: "text-2xl",
  }[size];

  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      {/* Precision Vector Emblem: Geometric Hexagonal Compass / Neural Spark */}
      <div
        className={`relative flex ${iconDimensions} shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 via-indigo-600 to-purple-600 shadow-md shadow-indigo-500/20 ring-1 ring-white/20`}
      >
        <svg
          viewBox="0 0 32 32"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="h-5/6 w-5/6 p-0.5 text-white drop-shadow-sm"
        >
          {/* Outer Guidestone Facets */}
          <path
            d="M16 3L27 9.5V22.5L16 29L5 22.5V9.5L16 3Z"
            stroke="currentColor"
            strokeWidth="1.75"
            strokeLinejoin="round"
            className="opacity-40"
          />
          {/* Dynamic Mentorship Compass / Ascending Diamond */}
          <path
            d="M16 6L23 16L16 26L9 16L16 6Z"
            fill="currentColor"
            fillOpacity="0.25"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
          {/* Inner Intelligence Core */}
          <circle cx="16" cy="16" r="3" fill="#ffffff" />
          <path
            d="M16 9V13M16 19V23M9 16H13M19 16H23"
            stroke="#ffffff"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
        </svg>
      </div>

      {/* Wordmark */}
      {showWordmark && (
        <div className="flex flex-col leading-tight">
          <div className="flex items-center gap-1.5">
            <span className={`font-bold tracking-tight text-white ${textSize}`}>
              Mentor
            </span>
            <span
              className={`rounded-md bg-indigo-500/15 px-1.5 py-0.2 font-semibold text-indigo-400 border border-indigo-500/30 text-[11px] uppercase tracking-wider`}
            >
              AI
            </span>
          </div>
          {subtitle && (
            <span className="text-[10px] uppercase font-medium tracking-wider text-zinc-400 mt-0.5">
              {subtitle}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
