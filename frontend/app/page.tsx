"use client";

import React from "react";
import Link from "next/link";
import {
  ArrowRight,
  Calendar,
  Cpu,
  Lock,
  ShieldCheck,
  Sparkles,
  Sliders,
  Terminal,
  Watch,
  CheckCircle2,
} from "lucide-react";
import { HealthStatusBadge } from "@/components/HealthStatusBadge";
import { MentorLogo } from "@/components/MentorLogo";
import { useAuth } from "@/lib/auth-context";

export default function LandingPage() {
  const { isAuthenticated } = useAuth();

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 selection:bg-indigo-500 selection:text-white">
      {/* Top Navbar */}
      <nav className="sticky top-0 z-30 border-b border-zinc-800/80 bg-zinc-950/80 backdrop-blur-xl px-4 sm:px-8 py-3.5">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <Link href="/" className="transition-opacity hover:opacity-90">
            <MentorLogo size="md" subtitle="Autonomous Task & Schedule Intelligence" />
          </Link>

          <div className="flex items-center gap-3">
            <HealthStatusBadge />
            {isAuthenticated ? (
              <Link
                href="/dashboard"
                className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-500 transition-all border border-indigo-400/30"
              >
                <span>Dashboard</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            ) : (
              <div className="flex items-center gap-2">
                <Link
                  href="/login"
                  className="rounded-xl px-3.5 py-1.5 text-xs font-medium text-zinc-300 hover:text-white hover:bg-zinc-900 transition-colors"
                >
                  Log In
                </Link>
                <Link
                  href="/signup"
                  className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-500 transition-all border border-indigo-400/30"
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
      <section className="relative px-4 pt-16 pb-20 sm:px-6 lg:px-8 text-center overflow-hidden">
        {/* Subtle Background Glow Elements */}
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-indigo-600/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative mx-auto max-w-3xl space-y-6">
          <div className="inline-flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3.5 py-1 text-xs font-semibold text-indigo-300">
            <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
            <span>Deterministic Task Orchestration & Scheduling</span>
          </div>

          <h1 className="text-4xl font-extrabold tracking-tight text-white sm:text-6xl leading-tight">
            Your Goals. Your Plan. <br />
            <span className="bg-gradient-to-r from-indigo-300 via-sky-200 to-indigo-100 bg-clip-text text-transparent">
              Your Next Move.
            </span>
          </h1>

          <p className="mx-auto max-w-2xl text-base sm:text-lg text-zinc-400 leading-relaxed">
            AI productivity and autonomous schedule intelligence engineered for students and professionals.
            Combines natural-language instruction reasoning with pure mathematical interval
            algebra to eliminate LLM hallucinations, guarantee zero calendar overlaps, and protect user privacy.
          </p>

          <div className="flex flex-wrap items-center justify-center gap-3 pt-4">
            {isAuthenticated ? (
              <Link
                href="/dashboard"
                className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white shadow-lg hover:bg-indigo-500 transition-all border border-indigo-400/30"
              >
                <span>Open Your Workspace</span>
                <ArrowRight className="h-4 w-4" />
              </Link>
            ) : (
              <>
                <Link
                  href="/signup"
                  className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white shadow-lg hover:bg-indigo-500 transition-all border border-indigo-400/30"
                >
                  <span>Get Started</span>
                  <ArrowRight className="h-4 w-4" />
                </Link>
                <Link
                  href="/login"
                  className="inline-flex items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-900/60 px-6 py-3 text-sm font-semibold text-zinc-200 hover:bg-zinc-800 hover:text-white transition-all backdrop-blur-md"
                >
                  <span>Sign In</span>
                </Link>
              </>
            )}
            <Link
              href="/planner"
              className="inline-flex items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-900/40 px-5 py-3 text-sm font-medium text-zinc-300 hover:text-white hover:bg-zinc-800/60 transition-all backdrop-blur-md"
            >
              <Terminal className="h-4 w-4 text-indigo-400" />
              <span>Natural-Language Input</span>
            </Link>
            <Link
              href="/watch"
              className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-800 bg-zinc-900/30 px-4 py-3 text-sm font-medium text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50 transition-all"
              title="Preview smartwatch companion mode"
            >
              <Watch className="h-4 w-4 text-emerald-400" />
              <span>Watch Mode</span>
            </Link>
          </div>
        </div>
      </section>

      {/* Core Architectural Guarantees */}
      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:px-8 border-t border-zinc-900">
        <div className="text-center space-y-2 mb-12">
          <h2 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
            Architectural Guarantees
          </h2>
          <p className="text-sm text-zinc-400 max-w-xl mx-auto">
            Engineered from first principles with formal safety constraints, truthfulness, and privacy by design.
          </p>
        </div>

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {/* Pillar 1 */}
          <div className="rounded-2xl border border-zinc-800/80 bg-zinc-900/40 p-6 space-y-3 backdrop-blur-md hover:border-zinc-700 transition-all">
            <div className="inline-flex rounded-xl bg-indigo-500/10 p-3 text-indigo-400 border border-indigo-500/20">
              <Sliders className="h-5 w-5" />
            </div>
            <h3 className="text-base font-semibold text-white">Deterministic Solver</h3>
            <p className="text-xs text-zinc-400 leading-relaxed">
              Pure Python interval algebra calculates mathematically conflict-free slots around fixed lectures, meetings, and buffer windows. Eliminates LLM time hallucinations.
            </p>
          </div>

          {/* Pillar 2 */}
          <div className="rounded-2xl border border-zinc-800/80 bg-zinc-900/40 p-6 space-y-3 backdrop-blur-md hover:border-zinc-700 transition-all">
            <div className="inline-flex rounded-xl bg-emerald-500/10 p-3 text-emerald-400 border border-emerald-500/20">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <h3 className="text-base font-semibold text-white">Two-Phase Human Approvals</h3>
            <p className="text-xs text-zinc-400 leading-relaxed">
              Consequential external actions (such as sending emails or publishing events) require explicit user confirmation. Actions are staged, verified, and audited.
            </p>
          </div>

          {/* Pillar 3 */}
          <div className="rounded-2xl border border-zinc-800/80 bg-zinc-900/40 p-6 space-y-3 backdrop-blur-md hover:border-zinc-700 transition-all">
            <div className="inline-flex rounded-xl bg-purple-500/10 p-3 text-purple-400 border border-purple-500/20">
              <Cpu className="h-5 w-5" />
            </div>
            <h3 className="text-base font-semibold text-white">Truthful AI Fallback</h3>
            <p className="text-xs text-zinc-400 leading-relaxed">
              Google Gemini intelligence with an automated deterministic rule engine fallback. Never invents missing deadlines or fake task durations.
            </p>
          </div>

          {/* Pillar 4 */}
          <div className="rounded-2xl border border-zinc-800/80 bg-zinc-900/40 p-6 space-y-3 backdrop-blur-md hover:border-zinc-700 transition-all">
            <div className="inline-flex rounded-xl bg-amber-500/10 p-3 text-amber-400 border border-amber-500/20">
              <Calendar className="h-5 w-5" />
            </div>
            <h3 className="text-base font-semibold text-white">Google Calendar Sync</h3>
            <p className="text-xs text-zinc-400 leading-relaxed">
              Least-privilege OAuth 2.0 integration with automatic token encryption at rest using AES-128 Fernet and automated token refresh.
            </p>
          </div>

          {/* Pillar 5 */}
          <div className="rounded-2xl border border-zinc-800/80 bg-zinc-900/40 p-6 space-y-3 backdrop-blur-md hover:border-zinc-700 transition-all">
            <div className="inline-flex rounded-xl bg-sky-500/10 p-3 text-sky-400 border border-sky-500/20">
              <Lock className="h-5 w-5" />
            </div>
            <h3 className="text-base font-semibold text-white">Multi-Tenant Isolation</h3>
            <p className="text-xs text-zinc-400 leading-relaxed">
              Cryptographically verified JWT sessions enforced by PostgreSQL Row Level Security (RLS) policies. User data is strictly isolated.
            </p>
          </div>

          {/* Pillar 6 */}
          <div className="rounded-2xl border border-zinc-800/80 bg-zinc-900/40 p-6 space-y-3 backdrop-blur-md hover:border-zinc-700 transition-all">
            <div className="inline-flex rounded-xl bg-rose-500/10 p-3 text-rose-400 border border-rose-500/20">
              <Terminal className="h-5 w-5" />
            </div>
            <h3 className="text-base font-semibold text-white">Model Context Protocol</h3>
            <p className="text-xs text-zinc-400 leading-relaxed">
              Native Python MCP SDK server exposing typed tools for AI agent integrations (Antigravity IDE, Claude, Cursor) with idempotency protection.
            </p>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-zinc-900 px-4 py-8 text-center text-xs text-zinc-500">
        <p className="font-semibold text-zinc-400">Mentor AI — Autonomous Task & Schedule Orchestration.</p>
        <p className="mt-1">
          Designed and built with Next.js 15, FastAPI, Python 3.12, Supabase PostgreSQL, and Google Antigravity.
        </p>
      </footer>
    </div>
  );
}
