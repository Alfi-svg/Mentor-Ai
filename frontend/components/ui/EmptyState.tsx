"use client";

import React from "react";
import { Sparkles } from "lucide-react";

export interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className = "",
}: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center p-8 text-center rounded-2xl border border-dashed border-[#233560] bg-[#0c1429]/50 ${className}`}
    >
      <div className="w-12 h-12 rounded-2xl bg-[#625BFF]/10 border border-[#625BFF]/20 flex items-center justify-center text-[#625BFF] mb-3">
        {icon || <Sparkles className="w-6 h-6 text-[#625BFF]" />}
      </div>
      <h4 className="text-sm font-semibold text-white tracking-tight">{title}</h4>
      {description && (
        <p className="text-xs text-slate-400 mt-1 max-w-sm leading-relaxed">
          {description}
        </p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
