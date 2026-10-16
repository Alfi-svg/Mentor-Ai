"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Calendar,
  CheckSquare,
  Clock,
  ExternalLink,
  Layers,
  LayoutDashboard,
  LogOut,
  Mail,
  Menu,
  MessageSquareCode,
  ShieldAlert,
  Sliders,
  Sparkles,
  User as UserIcon,
  X,
} from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { HealthStatusBadge } from "./HealthStatusBadge";
import { NotificationBell } from "./NotificationBell";

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const { user, isAuthenticated, isLoading, logout, sessionExpired, clearSessionExpired } =
    useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [isLoading, isAuthenticated, router]);

  // Close mobile menu on route change
  useEffect(() => {
    setMobileMenuOpen(false);
  }, [pathname]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950 text-zinc-100">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
          <p className="text-sm font-medium text-zinc-400">Loading your workspace...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null; // will redirect in useEffect
  }

  const navItems = [
    {
      href: "/dashboard",
      label: "Dashboard",
      icon: LayoutDashboard,
      description: "Overview & today's plan",
    },
    {
      href: "/planner",
      label: "AI Planner",
      icon: Sparkles,
      description: "Natural-language planning",
    },
    {
      href: "/schedule",
      label: "Schedule",
      icon: Clock,
      description: "Deterministic timeline",
    },
    {
      href: "/tasks",
      label: "Tasks",
      icon: CheckSquare,
      description: "Backlog & priorities",
    },
    {
      href: "/calendar",
      label: "Calendar",
      icon: Calendar,
      description: "Interactive calendar & tasks",
    },
    {
      href: "/gmail",
      label: "Gmail",
      icon: Mail,
      description: "Inbox & task extraction",
    },
    {
      href: "/actions",
      label: "Approvals & History",
      icon: ShieldAlert,
      description: "Two-phase human approval",
    },
    {
      href: "/settings/preferences",
      label: "Preferences",
      icon: Sliders,
      description: "Routines & work hours",
    },
  ];

  return (
    <div className="flex min-h-screen bg-zinc-950 text-zinc-100">
      {/* Sidebar for Desktop */}
      <aside className="hidden w-64 flex-col border-r border-zinc-800/80 bg-zinc-900/50 backdrop-blur-md md:flex">
        {/* Brand Header */}
        <div className="flex h-16 items-center gap-2.5 border-b border-zinc-800/80 px-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white shadow-sm font-bold text-base">
            M
          </div>
          <div>
            <span className="text-base font-semibold tracking-tight text-white">Mentor AI</span>
            <span className="block text-[10px] uppercase font-medium text-brand-400 tracking-wider">
              Autonomous Scheduler
            </span>
          </div>
        </div>

        {/* Navigation Items */}
        <nav className="flex-1 space-y-1 px-3 py-4">
          {navItems.map((item) => {
            const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-brand-600/15 text-brand-400 border border-brand-500/20"
                    : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                }`}
              >
                <Icon
                  className={`h-4 w-4 shrink-0 transition-colors ${
                    isActive ? "text-brand-400" : "text-zinc-400 group-hover:text-zinc-200"
                  }`}
                />
                <div className="flex flex-col">
                  <span>{item.label}</span>
                </div>
              </Link>
            );
          })}
        </nav>

        {/* Footer / User Profile & Logout */}
        <div className="border-t border-zinc-800/80 p-3">
          <div className="flex items-center justify-between rounded-lg bg-zinc-900/80 p-2.5 border border-zinc-800/60">
            <div className="flex items-center gap-2 overflow-hidden">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-zinc-300">
                <UserIcon className="h-3.5 w-3.5" />
              </div>
              <div className="truncate text-xs">
                <p className="truncate font-medium text-zinc-200">{user?.email || "Authenticated User"}</p>
                <p className="text-[10px] text-zinc-400">Authenticated Session</p>
              </div>
            </div>
            <button
              onClick={logout}
              title="Sign Out"
              className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-rose-400 transition-colors"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top Header */}
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-zinc-800/80 bg-zinc-950/80 px-4 backdrop-blur-md sm:px-6">
          <div className="flex items-center gap-3">
            {/* Mobile menu toggle */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="rounded-lg border border-zinc-800 p-2 text-zinc-400 hover:text-white md:hidden"
              aria-label="Toggle navigation menu"
            >
              {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
            <div className="hidden sm:block">
              <span className="text-xs uppercase tracking-wider text-zinc-400 font-semibold">
                Productivity Workspace
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Link
              href="/planner"
              className="hidden sm:inline-flex items-center gap-2 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-brand-500 transition-colors"
            >
              <Sparkles className="h-3.5 w-3.5" />
              <span>Ask Mentor</span>
            </Link>
            <NotificationBell />
            <HealthStatusBadge />
          </div>
        </header>

        {/* Mobile Navigation Drawer */}
        {mobileMenuOpen && (
          <div className="fixed inset-0 top-16 z-30 flex flex-col bg-zinc-950/95 backdrop-blur-lg border-b border-zinc-800 p-4 md:hidden">
            <nav className="space-y-1">
              {navItems.map((item) => {
                const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium ${
                      isActive
                        ? "bg-brand-600/20 text-brand-400 border border-brand-500/30"
                        : "text-zinc-400 hover:bg-zinc-900 hover:text-white"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </nav>
            <div className="mt-auto border-t border-zinc-800 pt-4 flex items-center justify-between">
              <span className="text-xs text-zinc-400 truncate max-w-[200px]">{user?.email}</span>
              <button
                onClick={logout}
                className="flex items-center gap-2 text-xs font-medium text-rose-400 hover:text-rose-300"
              >
                <LogOut className="h-3.5 w-3.5" />
                Sign Out
              </button>
            </div>
          </div>
        )}

        {/* Session Expired Notice */}
        {sessionExpired && (
          <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-xs text-amber-300 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 shrink-0 text-amber-400" />
              <span>Your session expired or was revoked. Please log in again to continue.</span>
            </div>
            <button
              onClick={clearSessionExpired}
              className="text-amber-400 hover:text-white font-medium underline"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Page Content Body */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
