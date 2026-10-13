"use client";

import React from "react";
import Link from "next/link";
import {
  ArrowRight,
  Calendar,
  CheckCircle,
  Cpu,
  Lock,
  ShieldCheck,
  Sparkles,
  Sliders,
  Terminal,
} from "lucide-react";
import { HealthStatusBadge } from "@/components/HealthStatusBadge";
import { useAuth } from "@/lib/auth-context";

export default function LandingPage() {
  const { isAuthenticated } = useAuth();

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 selection:bg-brand-500 selection:text-white">
      {/* Top Navbar */}
      <nav className="sticky top-0 z-30 border-b border-zinc-800/80 bg-zinc-950/80 backdrop-blur-md px-4 sm:px-8 py-3.5">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-white font-bold text-lg shadow-sm">
              M
            </div>
            <div>
              <span className="text-lg font-bold tracking-tight text-white">Mentor AI</span>
              <span className="hidden sm:inline-block ml-2 text-xs font-medium text-zinc-400">
                Your Goals. Your Plan. Your Next Move.
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <HealthStatusBadge />
            {isAuthenticated ? (
              <Link
                href="/dashboard"
                className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-brand-500 transition-colors"
              >
                <span>Dashboard</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            ) : (
              <div className="flex items-center gap-2">
                <Link
                  href="/login"
                  className="rounded-lg px-3 py-1.5 text-xs font-medium text-zinc-300 hover:text-white hover:bg-zinc-800/60 transition-colors"
                >
                  Log In
                </Link>
                <Link
                  href="/signup"
                  className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-brand-500 transition-colors"
                >
                  <span>Sign Up</span>
                  <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            )}
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative px-4 pt-16 pb-20 sm:px-6 lg:px-8 text-center">
        <div className="mx-auto max-w-3xl space-y-6">
          <div className="inline-flex items-center gap-2 rounded-full border border-brand-500/30 bg-brand-500/10 px-3.5 py-1 text-xs font-semibold text-brand-400">
            <Sparkles className="h-3.5 w-3.5" />
            <span>Deterministic AI Task Orchestration & Scheduling</span>
          </div>

          <h1 className="text-4xl font-extrabold tracking-tight text-white sm:text-6xl">
            Your Goals. Your Plan. <br />
            <span className="bg-gradient-to-r from-brand-400 to-sky-200 bg-clip-text text-transparent">
              Your Next Move.
            </span>
          </h1>

          <p className="mx-auto max-w-2xl text-base sm:text-lg text-zinc-400 leading-relaxed">
            Personal scheduling built for university students and professionals.
            Combines natural-language instruction parsing with pure mathematical interval
            scheduling to eliminate LLM hallucinations, guarantee zero calendar overlaps,
            and protect user privacy.
          </p>

          <div className="flex flex-wrap items-center justify-center gap-3 pt-4">
            {isAuthenticated ? (
              <Link
                href="/dashboard"
                className="inline-flex items-center gap-2 rounded-xl bg-brand-600 px-6 py-3 text-sm font-semibold text-white shadow-lg hover:bg-brand-500 transition-all"
              >
                <span>Open Your Workspace</span>
                <ArrowRight className="h-4 w-4" />
              </Link>
            ) : (
              <>
                <Link
                  href="/signup"
                  className="inline-flex items-center gap-2 rounded-xl bg-brand-600 px-6 py-3 text-sm font-semibold text-white shadow-lg hover:bg-brand-500 transition-all"
                >
                  <span>Get Started Free</span>
                  <ArrowRight className="h-4 w-4" />
                </Link>
                <Link
                  href="/login"
                  className="inline-flex items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-900/60 px-6 py-3 text-sm font-semibold text-zinc-200 hover:bg-zinc-800 hover:text-white transition-all"
                >
                  <span>Sign In</span>
                </Link>
              </>
            )}
            <Link
              href="/planner"
              className="inline-flex items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-900/40 px-5 py-3 text-sm font-medium text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/40 transition-all"
            >
              <Terminal className="h-4 w-4" />
              <span>Try Natural-Language Input</span>
            </Link>
          </div>
        </div>
      </section>

      {/* Core Architectural Guarantees */}
      <section className="mx-auto max-w-6xl px-4 py-12 sm:px-6 lg:px-8 border-t border-zinc-900">
        <div className="text-center space-y-2 mb-10">
          <h2 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
            Architectural Guarantees
          </h2>
          <p className="text-sm text-zinc-400 max-w-xl mx-auto">
            Engineered from first principles with formal safety constraints, truthfulness, and zero-budget feasibility.
          </p>
        </div>

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {/* Pillar 1 */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 space-y-3">
            <div className="inline-flex rounded-lg bg-blue-500/10 p-2.5 text-blue-400">
              <Sliders className="h-5 w-5" />
            </div>
            <h3 className="text-base font-semibold text-white">Deterministic Solver</h3>
            <p className="text-xs text-zinc-400 leading-relaxed">
              Pure Python interval algebra calculates mathematically conflict-free slots around fixed lectures, meetings, and buffer windows. Eliminates LLM time hallucinations.
            </p>
          </div>

          {/* Pillar 2 */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 space-y-3">
            <div className="inline-flex rounded-lg bg-emerald-500/10 p-2.5 text-emerald-400">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <h3 className="text-base font-semibold text-white">Two-Phase Human Approvals</h3>
            <p className="text-xs text-zinc-400 leading-relaxed">
              Consequential external actions (such as publishing calendar events) require explicit user confirmation. Actions are staged, verified, and recorded in an audit trail.
            </p>
          </div>

          {/* Pillar 3 */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 space-y-3">
            <div className="inline-flex rounded-lg bg-purple-500/10 p-2.5 text-purple-400">
              <Cpu className="h-5 w-5" />
            </div>
            <h3 className="text-base font-semibold text-white">Truthful AI Fallback</h3>
            <p className="text-xs text-zinc-400 leading-relaxed">
              Provider-agnostic adapter (Gemini Flash / Groq) with an automated deterministic rule engine fallback. Never invents missing deadlines or fake task durations.
            </p>
          </div>

          {/* Pillar 4 */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 space-y-3">
            <div className="inline-flex rounded-lg bg-amber-500/10 p-2.5 text-amber-400">
              <Calendar className="h-5 w-5" />
            </div>
            <h3 className="text-base font-semibold text-white">Google Calendar Sync</h3>
            <p className="text-xs text-zinc-400 leading-relaxed">
              Least-privilege OAuth 2.0 integration (<code className="text-[11px] text-amber-300">calendar.events</code>). Tokens are encrypted at rest with AES-128 Fernet and refreshed automatically.
            </p>
          </div>

          {/* Pillar 5 */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 space-y-3">
            <div className="inline-flex rounded-lg bg-sky-500/10 p-2.5 text-sky-400">
              <Lock className="h-5 w-5" />
            </div>
            <h3 className="text-base font-semibold text-white">Multi-Tenant Isolation</h3>
            <p className="text-xs text-zinc-400 leading-relaxed">
              Supabase Auth JWT verification at the API gateway enforced by PostgreSQL Row Level Security (RLS) policies. User A can never inspect or alter User B data.
            </p>
          </div>

          {/* Pillar 6 */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 space-y-3">
            <div className="inline-flex rounded-lg bg-rose-500/10 p-2.5 text-rose-400">
              <Terminal className="h-5 w-5" />
            </div>
            <h3 className="text-base font-semibold text-white">Model Context Protocol</h3>
            <p className="text-xs text-zinc-400 leading-relaxed">
              Native Python MCP SDK server exposing 8 typed tools for AI agent integrations (Antigravity IDE, Claude Desktop, Cursor) with idempotency protection.
            </p>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-zinc-900 px-4 py-8 text-center text-xs text-zinc-500">
        <p>Mentor AI — Autonomous Task & Schedule Orchestration. Strict Zero-Budget Architecture.</p>
        <p className="mt-1">
          Designed and built with Next.js 15, FastAPI, Python 3.12, Supabase PostgreSQL, and Google Antigravity.
        </p>
      </footer>
    </div>
  );
}
