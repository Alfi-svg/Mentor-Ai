"use client";

import React, { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle, RefreshCw, Home } from "lucide-react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log error securely on client without leaking credentials
    console.error("Mentor AI runtime caught an application exception:", error.message);
  }, [error]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-950 px-4 py-12 text-zinc-100 sm:px-6 lg:px-8">
      <div className="w-full max-w-md space-y-6 rounded-2xl border border-zinc-800/80 bg-zinc-900/60 p-8 text-center shadow-2xl backdrop-blur-md">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-rose-500/10 text-rose-400 border border-rose-500/20">
          <AlertTriangle className="h-6 w-6" />
        </div>

        <div className="space-y-2">
          <h1 className="text-xl font-bold tracking-tight text-white sm:text-2xl">
            Something Went Wrong
          </h1>
          <p className="text-xs text-zinc-400">
            A temporary client exception occurred while loading this view. Your saved data is safe.
          </p>
        </div>

        {error.message && (
          <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3 text-left">
            <p className="text-[11px] font-mono text-zinc-400 break-all">
              {error.message}
            </p>
          </div>
        )}

        <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
          <button
            onClick={() => reset()}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-xs font-semibold text-white shadow-sm hover:bg-brand-500 transition-colors"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Try Again</span>
          </button>
          <Link
            href="/dashboard"
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2.5 text-xs font-semibold text-zinc-200 hover:bg-zinc-700 hover:text-white transition-colors"
          >
            <Home className="h-3.5 w-3.5" />
            <span>Dashboard</span>
          </Link>
        </div>
      </div>
    </div>
  );
}
