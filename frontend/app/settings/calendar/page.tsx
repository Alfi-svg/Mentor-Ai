"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Calendar, RefreshCw } from "lucide-react";
import { AppShell } from "@/components/AppShell";

export default function CalendarSettingsRedirectPage() {
  const router = useRouter();

  useEffect(() => {
    if (typeof window !== "undefined") {
      const currentSearch = window.location.search;
      const targetParams = new URLSearchParams(currentSearch);
      targetParams.set("settings", "open");
      router.replace(`/calendar?${targetParams.toString()}`);
    }
  }, [router]);

  return (
    <AppShell>
      <div className="flex min-h-[60vh] flex-col items-center justify-center space-y-4 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-500/10 text-brand-400">
          <Calendar className="h-6 w-6 animate-pulse" />
        </div>
        <div className="space-y-1">
          <h2 className="text-lg font-semibold text-white">Redirecting to Calendar Workspace...</h2>
          <p className="text-xs text-zinc-400">
            Calendar sync settings and controls are now integrated directly into the workspace.
          </p>
        </div>
        <Link
          href="/calendar?settings=open"
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-xs font-medium text-white hover:bg-brand-500 transition-colors"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          <span>Open Calendar Settings</span>
        </Link>
      </div>
    </AppShell>
  );
}
