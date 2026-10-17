"use client";

import React, { useEffect, useState } from "react";
import { fetchHealth, type HealthStatus } from "@/lib/api";
import { CheckCircle2, AlertCircle, RefreshCw } from "lucide-react";

export function HealthStatusBadge() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [isWakingUp, setIsWakingUp] = useState<boolean>(false);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const [mounted, setMounted] = useState<boolean>(false);

  const checkStatus = async () => {
    setLoading(true);
    // If request takes longer than 2.5s, inform the user about server spinning up
    const wakeTimer = setTimeout(() => {
      setIsWakingUp(true);
    }, 2500);

    const data = await fetchHealth();
    clearTimeout(wakeTimer);
    setIsWakingUp(false);
    setHealth(data);
    setLoading(false);
    setLastChecked(new Date());
  };

  useEffect(() => {
    setMounted(true);
    checkStatus();
    // Poll every 30 seconds
    const interval = setInterval(checkStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex items-center gap-2.5 rounded-xl border border-zinc-800/80 bg-zinc-900/60 px-3 py-1.5 text-xs text-zinc-300 backdrop-blur-md shadow-sm">
      <div className="flex items-center gap-2">
        {loading ? (
          <RefreshCw className="h-3.5 w-3.5 animate-spin text-zinc-500" />
        ) : health ? (
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
        ) : (
          <AlertCircle className="h-3.5 w-3.5 text-amber-400" />
        )}
        <span className="hidden sm:inline font-medium text-zinc-400">
          API:
        </span>
        <span
          className={
            health
              ? "font-mono font-semibold text-emerald-400"
              : isWakingUp
              ? "font-mono font-semibold text-indigo-400"
              : "font-mono font-semibold text-amber-400"
          }
        >
          {isWakingUp
            ? "Server spinning up..."
            : loading
            ? "Checking..."
            : health
            ? `Online (v${health.version})`
            : "Connecting..."}
        </span>
      </div>

      <button
        onClick={checkStatus}
        className="ml-auto inline-flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-200 transition-colors"
        title={mounted && lastChecked ? `Last checked: ${lastChecked.toLocaleTimeString()}` : "Check backend status"}
      >
        <RefreshCw className="h-3 w-3" />
        <span className="hidden md:inline">Check</span>
      </button>
    </div>
  );
}
