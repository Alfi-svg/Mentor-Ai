"use client";

import React, { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle, RefreshCw, LayoutDashboard } from "lucide-react";
import { AppShell } from "@/components/AppShell";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Dashboard error caught:", error.message);
  }, [error]);

  return (
    <AppShell>
      <div className="flex min-h-[60vh] flex-col items-center justify-center px-4 text-center">
        <div className="w-full max-w-md space-y-5 rounded-2xl border border-zinc-800/80 bg-zinc-900/40 p-8 shadow-xl">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <AlertTriangle className="h-6 w-6" />
          </div>

          <div className="space-y-1">
            <h2 className="text-lg font-bold text-white">
              Dashboard Temporarily Unavailable
            </h2>
            <p className="text-xs text-zinc-400">
              Failed to load some dashboard metrics. The backend server might be spinning up or synchronizing.
            </p>
          </div>

          {error.message && (
            <p className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-2.5 text-[11px] font-mono text-zinc-400">
              {error.message}
            </p>
          )}

          <div className="flex justify-center gap-3">
            <button
              onClick={() => reset()}
              className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-xs font-semibold text-white hover:bg-brand-500 transition-colors"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              <span>Retry Dashboard</span>
            </button>
            <Link
              href="/tasks"
              className="inline-flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 text-xs font-semibold text-zinc-300 hover:bg-zinc-700 transition-colors"
            >
              <LayoutDashboard className="h-3.5 w-3.5" />
              <span>Go to Tasks</span>
            </Link>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
