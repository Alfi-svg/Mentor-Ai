"use client";

import React, { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { CopilotDrawer } from "@/components/copilot/CopilotDrawer";
import { CopilotVoiceOrb, OrbState } from "@/components/copilot/CopilotVoiceOrb";
import {
  BookOpen,
  Calendar,
  Code,
  Mail,
  Mic,
  Sparkles,
} from "lucide-react";

export default function CopilotPage() {
  const [drawerOpen, setDrawerOpen] = useState(true);
  const [orbState, setOrbState] = useState<OrbState>("idle");

  return (
    <AppShell>
      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-10rem)] p-6 text-center">
        {/* Ambient Glow */}
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-indigo-600/10 rounded-full blur-3xl pointer-events-none" />

        {/* Hero Visualizer */}
        <div className="relative mb-6">
          <CopilotVoiceOrb
            state={orbState}
            size={200}
            onClick={() => setDrawerOpen(true)}
          />
        </div>

        <div className="relative max-w-xl">
          <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 text-xs font-semibold mb-3 backdrop-blur-md">
            <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
            <span>Autonomous Voice & Schedule Assistant</span>
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-white sm:text-4xl">
            Mentor AI Copilot
          </h1>
          <p className="mt-3 text-sm text-zinc-400 leading-relaxed">
            Your personal educational assistant for schedule awareness, academic concepts,
            programming tutoring, authoritative study resources, and student accountability.
          </p>

          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <button
              onClick={() => setDrawerOpen(true)}
              className="flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg hover:bg-indigo-500 transition-all border border-indigo-400/30"
            >
              <Mic className="h-4 w-4" />
              <span>Launch Voice Assistant</span>
            </button>
          </div>
        </div>

        {/* Feature Grid */}
        <div className="relative mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 max-w-4xl text-left">
          <div className="rounded-2xl border border-zinc-800/80 bg-zinc-900/40 p-5 backdrop-blur-md hover:border-zinc-700 transition-all">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 mb-3">
              <Calendar className="h-4 w-4" />
            </div>
            <h3 className="text-sm font-semibold text-white">Schedule Intelligence</h3>
            <p className="mt-1 text-xs text-zinc-400 leading-relaxed">
              Instant chronological awareness of today&apos;s classes, task blocks, and deadlines.
            </p>
          </div>

          <div className="rounded-2xl border border-zinc-800/80 bg-zinc-900/40 p-5 backdrop-blur-md hover:border-zinc-700 transition-all">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 mb-3">
              <BookOpen className="h-4 w-4" />
            </div>
            <h3 className="text-sm font-semibold text-white">Educational Search</h3>
            <p className="mt-1 text-xs text-zinc-400 leading-relaxed">
              Verified university courses, video lectures, and official technical documentation.
            </p>
          </div>

          <div className="rounded-2xl border border-zinc-800/80 bg-zinc-900/40 p-5 backdrop-blur-md hover:border-zinc-700 transition-all">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 mb-3">
              <Code className="h-4 w-4" />
            </div>
            <h3 className="text-sm font-semibold text-white">Programming Tutor</h3>
            <p className="mt-1 text-xs text-zinc-400 leading-relaxed">
              Focused, step-by-step tutoring with strict 100-line modular examples.
            </p>
          </div>

          <div className="rounded-2xl border border-zinc-800/80 bg-zinc-900/40 p-5 backdrop-blur-md hover:border-zinc-700 transition-all">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 mb-3">
              <Mail className="h-4 w-4" />
            </div>
            <h3 className="text-sm font-semibold text-white">Safe Gmail Copilot</h3>
            <p className="mt-1 text-xs text-zinc-400 leading-relaxed">
              Disambiguated thread context and preview drafts requiring explicit confirmation.
            </p>
          </div>
        </div>

        {/* Global Copilot Drawer */}
        <CopilotDrawer
          isOpen={drawerOpen}
          onClose={() => setDrawerOpen(false)}
        />
      </div>
    </AppShell>
  );
}
