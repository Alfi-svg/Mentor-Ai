"use client";

import React, { useEffect, useState } from "react";
import { fetchHealth, type HealthStatus } from "@/lib/api";
import { CheckCircle2, AlertCircle, RefreshCw } from "lucide-react";

export function HealthStatusBadge() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [isWakingUp, setIsWakingUp] = useState<boolean>(false);
  const [lastChecked, setLastChecked] = useState<Date>(new Date());

  const checkStatus = async () => {
    setLoading(true);
    // If request takes longer than 2.5s, inform the user about free-tier cold start
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
    checkStatus();
    // Poll every 30 seconds
    const interval = setInterval(checkStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex items-center gap-3 rounded-lg border border-zinc-200 bg-zinc-50 px-3.5 py-2 text-xs dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex items-center gap-2">
        {loading ? (
          <RefreshCw className="h-3.5 w-3.5 animate-spin text-zinc-500" />
        ) : health ? (
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
        ) : (
          <AlertCircle className="h-3.5 w-3.5 text-amber-500" />
        )}
        <span className="font-medium text-zinc-700 dark:text-zinc-300">
          Backend API:
        </span>
        <span
          className={
            health
              ? "font-mono font-semibold text-emerald-600 dark:text-emerald-400"
              : isWakingUp
              ? "font-mono font-semibold text-indigo-600 dark:text-indigo-400"
              : "font-mono font-semibold text-amber-600 dark:text-amber-400"
          }
        >
          {isWakingUp
            ? "Waking up server (free-tier spin-up ~50s)..."
            : loading
            ? "Checking..."
            : health
            ? `Online (v${health.version})`
            : "Offline / Connecting..."}
        </span>
      </div>

      <button
        onClick={checkStatus}
        className="ml-auto inline-flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
        title={`Last checked: ${lastChecked.toLocaleTimeString()}`}
      >
        <RefreshCw className="h-3 w-3" />
        <span>Check</span>
      </button>
    </div>
  );
}
