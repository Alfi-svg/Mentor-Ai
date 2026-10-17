"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Mail, RefreshCw } from "lucide-react";
import { AppShell } from "@/components/AppShell";

export default function GmailSettingsRedirectPage() {
  const router = useRouter();

  useEffect(() => {
    if (typeof window !== "undefined") {
      const currentSearch = window.location.search;
      const targetParams = new URLSearchParams(currentSearch);
      targetParams.set("settings", "open");
      router.replace(`/gmail?${targetParams.toString()}`);
    }
  }, [router]);

  return (
    <AppShell>
      <div className="flex min-h-[60vh] flex-col items-center justify-center space-y-4 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-500/10 text-brand-400">
          <Mail className="h-6 w-6 animate-pulse" />
        </div>
        <div className="space-y-1">
          <h2 className="text-lg font-semibold text-white">Redirecting to Gmail Workspace...</h2>
          <p className="text-xs text-zinc-400">
            Gmail connection settings and permissions are now integrated directly into the workspace.
          </p>
        </div>
        <Link
          href="/gmail?settings=open"
          className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 transition-all border border-indigo-400/30"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          <span>Open Gmail Settings</span>
        </Link>
      </div>
    </AppShell>
  );
}
