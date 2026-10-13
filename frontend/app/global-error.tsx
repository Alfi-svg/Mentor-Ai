"use client";

import React, { useEffect } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Mentor AI global layout exception:", error.message);
  }, [error]);

  return (
    <html lang="en">
      <body className="flex min-h-screen items-center justify-center bg-zinc-950 px-4 text-zinc-100">
        <div className="w-full max-w-md space-y-6 rounded-2xl border border-zinc-800/80 bg-zinc-900/60 p-8 text-center shadow-2xl backdrop-blur-md">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <AlertTriangle className="h-6 w-6" />
          </div>

          <div className="space-y-2">
            <h1 className="text-xl font-bold tracking-tight text-white">
              Application Error
            </h1>
            <p className="text-xs text-zinc-400">
              An unexpected error occurred while rendering the workspace layout.
            </p>
          </div>

          <button
            onClick={() => reset()}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-xs font-semibold text-white shadow-sm hover:bg-brand-500 transition-colors"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Reload Application</span>
          </button>
        </div>
      </body>
    </html>
  );
}
