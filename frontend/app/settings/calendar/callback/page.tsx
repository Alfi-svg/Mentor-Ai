"use client";

import React, { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { CheckCircle2, AlertTriangle, ArrowRight } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { apiClient, ApiClientError } from "@/lib/api-client";

function CallbackHandler() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const code = searchParams.get("code");
  const state = searchParams.get("state");

  const [loading, setLoading] = useState(true);
  const [success, setSuccess] = useState(false);
  const [accountEmail, setAccountEmail] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function exchangeOAuth() {
      if (!code || !state) {
        setError("Missing OAuth authorization code or state token.");
        setLoading(false);
        return;
      }

      try {
        const res = await apiClient.handleCalendarCallback(code, state);
        setSuccess(true);
        setAccountEmail(res.account_email);
        setTimeout(() => {
          router.push("/settings/calendar");
        }, 2500);
      } catch (err) {
        if (err instanceof ApiClientError) {
          setError(err.message);
        } else {
          setError("Failed to complete Google Calendar authentication.");
        }
      } finally {
        setLoading(false);
      }
    }

    exchangeOAuth();
  }, [code, state, router]);

  return (
    <div className="mx-auto max-w-lg rounded-2xl border border-zinc-800 bg-zinc-900/60 p-8 text-center space-y-4 shadow-xl">
      {loading && (
        <div className="space-y-3">
          <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
          <h2 className="text-base font-bold text-white">Connecting Google Calendar...</h2>
          <p className="text-xs text-zinc-400">
            Verifying cryptographic CSRF signature and exchanging authorization code.
          </p>
        </div>
      )}

      {!loading && success && (
        <div className="space-y-3">
          <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-400" />
          <h2 className="text-base font-bold text-white">Calendar Connected!</h2>
          <p className="text-xs text-emerald-300">
            Successfully authorized for <strong>{accountEmail}</strong>. Redirecting to calendar
            dashboard...
          </p>
          <Link
            href="/settings/calendar"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-brand-400 hover:underline pt-2"
          >
            <span>Go to Calendar Settings Now</span>
            <ArrowRight className="h-3 w-3" />
          </Link>
        </div>
      )}

      {!loading && error && (
        <div className="space-y-3">
          <AlertTriangle className="mx-auto h-10 w-10 text-rose-400" />
          <h2 className="text-base font-bold text-white">Connection Failed</h2>
          <p className="text-xs text-rose-300">{error}</p>
          <Link
            href="/settings/calendar"
            className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-800 px-4 py-2 text-xs font-semibold text-white hover:bg-zinc-700 pt-2"
          >
            <span>Return to Calendar Settings</span>
          </Link>
        </div>
      )}
    </div>
  );
}

export default function CalendarCallbackPage() {
  return (
    <AppShell>
      <div className="flex min-h-[60vh] items-center justify-center p-4">
        <Suspense
          fallback={
            <div className="text-xs text-zinc-400">Loading authorization parameters...</div>
          }
        >
          <CallbackHandler />
        </Suspense>
      </div>
    </AppShell>
  );
}
