"use client";

import React, { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  Github,
  Linkedin,
  ExternalLink,
  Code2,
  Sparkles,
  Cpu,
  Layers,
  ShieldCheck,
  Calendar,
  CheckCircle2,
  Terminal,
  User,
  Heart,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { TEAM_INFO, TeamMember } from "@/lib/team-data";

function MemberAvatar({ member }: { member: TeamMember }) {
  const [imgError, setImgError] = useState(false);

  // Initials fallback
  const initials = member.name
    .split(" ")
    .map((n) => n[0])
    .slice(0, 2)
    .join("");

  if (member.avatarUrl && !imgError) {
    return (
      <div className="relative h-24 w-24 shrink-0 sm:h-28 sm:w-28 overflow-hidden rounded-2xl border-2 border-indigo-500/30 bg-zinc-900 shadow-lg shadow-indigo-500/10 ring-2 ring-zinc-800/80 transition-transform duration-300 group-hover:scale-105 group-hover:border-indigo-400/60">
        <Image
          src={member.avatarUrl}
          alt={member.name}
          width={112}
          height={112}
          className="h-full w-full object-cover object-center"
          onError={() => setImgError(true)}
          priority
        />
      </div>
    );
  }

  return (
    <div className="flex h-24 w-24 shrink-0 sm:h-28 sm:w-28 items-center justify-center rounded-2xl border-2 border-indigo-500/30 bg-gradient-to-tr from-indigo-950 via-zinc-900 to-purple-950 shadow-lg shadow-indigo-500/10 ring-2 ring-zinc-800/80 transition-transform duration-300 group-hover:scale-105 group-hover:border-indigo-400/60">
      <span className="font-mono text-xl sm:text-2xl font-bold tracking-wider text-indigo-300">
        {initials || <User className="h-8 w-8 text-indigo-300" />}
      </span>
    </div>
  );
}

function MemberCard({ member }: { member: TeamMember }) {
  return (
    <div className="group relative flex flex-col justify-between rounded-2xl border border-zinc-800/80 bg-zinc-900/40 p-6 sm:p-7 backdrop-blur-xl shadow-xl transition-all duration-300 hover:border-indigo-500/40 hover:bg-zinc-900/60 hover:shadow-2xl hover:shadow-indigo-500/10">
      {/* Subtle background glow effect */}
      <div className="pointer-events-none absolute -inset-px rounded-2xl opacity-0 transition-opacity duration-300 group-hover:opacity-100 bg-gradient-to-br from-indigo-500/10 via-purple-500/5 to-transparent" />

      <div className="relative space-y-5">
        {/* Header with Avatar and Basic Info */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 sm:gap-5">
          <MemberAvatar member={member} />

          <div className="space-y-1.5 flex-1 min-w-0">
            <div className="inline-flex items-center gap-1.5 rounded-full bg-indigo-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-indigo-300 border border-indigo-500/20">
              <Sparkles className="h-3 w-3 text-indigo-400" />
              <span>{member.role || "Developer"}</span>
            </div>
            <h3 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
              {member.name}
            </h3>
            <p className="text-xs text-zinc-400 leading-relaxed">
              {member.bio}
            </p>
          </div>
        </div>

        {/* Contributions Checklist */}
        {member.contributions && member.contributions.length > 0 && (
          <div className="rounded-xl border border-zinc-800/70 bg-zinc-950/60 p-4 space-y-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 block">
              Core Architectural Focus
            </span>
            <ul className="space-y-1.5">
              {member.contributions.map((item, idx) => (
                <li
                  key={idx}
                  className="flex items-center gap-2 text-xs text-zinc-300"
                >
                  <CheckCircle2 className="h-3.5 w-3.5 text-indigo-400 shrink-0" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Social Links Footer */}
      <div className="relative mt-6 pt-5 border-t border-zinc-800/80 flex flex-wrap items-center gap-3">
        <a
          href={member.githubUrl}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Visit ${member.name}'s GitHub profile`}
          className="inline-flex items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-950/80 px-3.5 py-2 text-xs font-semibold text-zinc-300 transition-all hover:border-zinc-700 hover:bg-zinc-800 hover:text-white hover:shadow-md"
        >
          <Github className="h-4 w-4 text-zinc-300" />
          <span>GitHub</span>
          <ExternalLink className="h-3 w-3 text-zinc-500" />
        </a>

        <a
          href={member.linkedinUrl}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Visit ${member.name}'s LinkedIn profile`}
          className="inline-flex items-center gap-2 rounded-xl border border-sky-500/20 bg-sky-500/10 px-3.5 py-2 text-xs font-semibold text-sky-300 transition-all hover:border-sky-500/40 hover:bg-sky-500/20 hover:text-sky-200 hover:shadow-md"
        >
          <Linkedin className="h-4 w-4 text-sky-400" />
          <span>LinkedIn</span>
          <ExternalLink className="h-3 w-3 text-sky-400/70" />
        </a>
      </div>
    </div>
  );
}

export default function TeamPage() {
  const [logoError, setLogoError] = useState(false);

  return (
    <AppShell requireAuth={false}>
      <div className="mx-auto max-w-6xl space-y-10">
        {/* Top Hero Section */}
        <section className="relative overflow-hidden rounded-3xl border border-zinc-800/80 bg-gradient-to-b from-indigo-950/20 via-zinc-900/40 to-zinc-950/80 p-6 sm:p-10 backdrop-blur-xl">
          {/* Subtle Ambient Glow */}
          <div className="pointer-events-none absolute -top-24 left-1/2 -translate-x-1/2 h-64 w-96 rounded-full bg-indigo-600/15 blur-3xl" />

          <div className="relative flex flex-col md:flex-row items-center justify-between gap-6 md:gap-8">
            <div className="space-y-3 text-center md:text-left">
              <div className="inline-flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3.5 py-1 text-xs font-semibold text-indigo-300 shadow-sm">
                <Code2 className="h-3.5 w-3.5 text-indigo-400" />
                <span>The Engineering Minds</span>
              </div>

              <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight text-white">
                Meet Our Team
              </h1>

              <p className="text-sm sm:text-base text-zinc-400 max-w-2xl">
                Meet the people behind Mentor AI. Dedicated engineers building autonomous, deterministic educational copilots.
              </p>
            </div>

            {/* Team Brand Badge / Logo Banner */}
            <div className="flex flex-col items-center justify-center rounded-2xl border border-zinc-800 bg-zinc-900/70 p-5 sm:p-6 backdrop-blur-md shadow-xl text-center shrink-0 min-w-[240px]">
              {TEAM_INFO.logoUrl && !logoError ? (
                <div className="mb-3 h-16 w-16 overflow-hidden rounded-xl border border-indigo-500/30 bg-zinc-950 p-2 shadow-inner">
                  <Image
                    src={TEAM_INFO.logoUrl}
                    alt={TEAM_INFO.name}
                    width={64}
                    height={64}
                    className="h-full w-full object-contain"
                    onError={() => setLogoError(true)}
                  />
                </div>
              ) : (
                <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-xl bg-indigo-600/20 text-indigo-300 border border-indigo-500/30">
                  <Terminal className="h-7 w-7 text-indigo-400" />
                </div>
              )}

              <span className="text-[10px] font-bold uppercase tracking-widest text-indigo-400">
                TEAM CREATORS
              </span>
              <h2 className="text-xl font-extrabold tracking-wider text-white mt-0.5">
                {TEAM_INFO.name.toUpperCase()}
              </h2>
              <p className="mt-1 text-xs font-mono text-zinc-400">
                &ldquo;{TEAM_INFO.tagline}&rdquo;
              </p>
            </div>
          </div>
        </section>

        {/* Team Members Grid */}
        <section className="space-y-6">
          <div className="flex items-center justify-between border-b border-zinc-800/80 pb-3">
            <div>
              <h2 className="text-lg font-bold text-white tracking-tight">
                Core Engineers &amp; Architects
              </h2>
              <p className="text-xs text-zinc-400">
                Direct contributors to the Mentor AI full-stack architecture.
              </p>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-zinc-500 font-mono">
              <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-glow-emerald" />
              <span>2 Active Authors</span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 lg:gap-8">
            {TEAM_INFO.members.map((member) => (
              <MemberCard key={member.id} member={member} />
            ))}
          </div>
        </section>

        {/* Mission & Technology Stack Summary */}
        <section className="rounded-2xl border border-zinc-800/80 bg-zinc-900/30 p-6 sm:p-8 backdrop-blur-md">
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
            <div className="space-y-2 max-w-2xl">
              <div className="flex items-center gap-2 text-indigo-400 font-semibold text-xs">
                <Layers className="h-4 w-4" />
                <span>ABOUT CODE ARENAX &amp; MENTOR AI</span>
              </div>
              <h3 className="text-lg sm:text-xl font-bold text-white">
                Engineered for Academic Rigor &amp; Autonomous Productivity
              </h3>
              <p className="text-xs sm:text-sm text-zinc-400 leading-relaxed">
                Mentor AI was conceived and implemented by Code ArenaX to combine
                generative multimodal intelligence (Gemini 2.5 Flash) with deterministic task scheduling,
                tight Google Calendar 2-way synchronization, and strict multi-tenant database isolation.
              </p>
            </div>

            <div className="flex flex-wrap gap-2 sm:max-w-xs">
              <span className="rounded-lg border border-zinc-800 bg-zinc-950/80 px-2.5 py-1 text-[11px] font-mono text-zinc-400">
                Next.js 15 App Router
              </span>
              <span className="rounded-lg border border-zinc-800 bg-zinc-950/80 px-2.5 py-1 text-[11px] font-mono text-zinc-400">
                FastAPI Python 3.12
              </span>
              <span className="rounded-lg border border-zinc-800 bg-zinc-950/80 px-2.5 py-1 text-[11px] font-mono text-zinc-400">
                Gemini Flash LLM &amp; STT
              </span>
              <span className="rounded-lg border border-zinc-800 bg-zinc-950/80 px-2.5 py-1 text-[11px] font-mono text-zinc-400">
                Supabase PostgreSQL RLS
              </span>
              <span className="rounded-lg border border-zinc-800 bg-zinc-950/80 px-2.5 py-1 text-[11px] font-mono text-zinc-400">
                Google Calendar OAuth
              </span>
              <span className="rounded-lg border border-zinc-800 bg-zinc-950/80 px-2.5 py-1 text-[11px] font-mono text-zinc-400">
                Model Context Protocol
              </span>
            </div>
          </div>
        </section>
      </div>
    </AppShell>
  );
}
