"use client";

import React, { useState } from "react";
import { AlertCircle, RefreshCw, ChevronDown, ChevronUp, ServerCrash } from "lucide-react";

export interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void | Promise<void>;
  retryLabel?: string;
  isRetrying?: boolean;
  details?: string;
  action?: React.ReactNode;
  compact?: boolean;
}

export function ErrorState({
  title = "Unable to connect to Mentor AI backend",
  message = "Please check your network connection or verify that the backend API service is running.",
  onRetry,
  retryLabel = "Retry Connection",
  isRetrying = false,
  details,
  action,
  compact = false,
}: ErrorStateProps) {
  const [showDetails, setShowDetails] = useState(false);

  if (compact) {
    return (
      <div className="flex items-center justify-between gap-3 p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-200 text-xs">
        <div className="flex items-center gap-2 min-w-0">
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
          <span className="truncate">{title}: {message}</span>
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            disabled={isRetrying}
            className="px-2.5 py-1 text-xs font-medium rounded-lg bg-rose-600 hover:bg-rose-500 text-white shrink-0 flex items-center gap-1.5 transition disabled:opacity-50"
          >
            <RefreshCw className={`w-3 h-3 ${isRetrying ? "animate-spin" : ""}`} />
            <span>{isRetrying ? "Retrying..." : retryLabel}</span>
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center p-8 text-center rounded-2xl bg-[#0d162e]/90 border border-rose-500/20 shadow-xl max-w-lg mx-auto">
      <div className="w-14 h-14 rounded-2xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400 mb-4 shadow-lg shadow-rose-950/40">
        <ServerCrash className="w-7 h-7" />
      </div>

      <h3 className="text-base font-semibold text-white tracking-tight">{title}</h3>
      <p className="text-xs text-slate-300 mt-2 max-w-md leading-relaxed">{message}</p>

      <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            disabled={isRetrying}
            className="px-4 py-2 text-xs font-semibold rounded-xl bg-[#625BFF] hover:bg-[#5248E5] text-white shadow-lg shadow-[#625BFF]/30 transition flex items-center gap-2 focus:outline-none focus:ring-2 focus:ring-[#625BFF] disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRetrying ? "animate-spin" : ""}`} />
            <span>{isRetrying ? "Retrying..." : retryLabel}</span>
          </button>
        )}
        {action}
      </div>

      {details && (
        <div className="mt-4 w-full text-left">
          <button
            type="button"
            onClick={() => setShowDetails(!showDetails)}
            className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-slate-200 transition mx-auto"
          >
            <span>{showDetails ? "Hide technical diagnostic" : "Show technical diagnostic"}</span>
            {showDetails ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>

          {showDetails && (
            <pre className="mt-2 p-3 rounded-lg bg-black/40 border border-white/5 text-[10px] text-slate-400 font-mono overflow-x-auto whitespace-pre-wrap max-h-40">
              {details}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
