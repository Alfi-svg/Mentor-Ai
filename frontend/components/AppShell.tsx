"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Calendar,
  CheckSquare,
  Clock,
  LayoutDashboard,
  LogOut,
  Mail,
  Menu,
  ShieldAlert,
  Sliders,
  Sparkles,
  User as UserIcon,
  X,
  ChevronRight,
  Compass,
  Users,
} from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { HealthStatusBadge } from "./HealthStatusBadge";
import { NotificationBell } from "./NotificationBell";
import { CopilotDrawer } from "./copilot/CopilotDrawer";
import { MentorLogo } from "./MentorLogo";

interface AppShellProps {
  children: React.ReactNode;
  requireAuth?: boolean;
}

interface NavGroup {
  title: string;
  items: {
    href: string;
    label: string;
    icon: React.ComponentType<{ className?: string }>;
    badge?: string;
  }[];
}

export function AppShell({ children, requireAuth = true }: AppShellProps) {
  const { user, isAuthenticated, isLoading, logout, sessionExpired, clearSessionExpired } =
    useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [copilotOpen, setCopilotOpen] = useState(false);

  useEffect(() => {
    if (requireAuth && !isLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [requireAuth, isLoading, isAuthenticated, router]);

  // Close mobile menu on route change
  useEffect(() => {
    setMobileMenuOpen(false);
  }, [pathname]);

  // Global keyboard shortcut: Cmd+K / Ctrl+K opens Copilot
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCopilotOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950 text-zinc-100">
        <div className="flex flex-col items-center gap-4">
          <MentorLogo size="lg" showWordmark={true} subtitle="Loading Workspace..." />
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent mt-2" />
        </div>
      </div>
    );
  }

  // If public viewing is allowed and user is not authenticated
  if (!isAuthenticated && !requireAuth) {
    return (
      <div className="flex min-h-screen flex-col bg-zinc-950 text-zinc-100 antialiased selection:bg-indigo-500 selection:text-white">
        {/* Public Navigation Header */}
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-zinc-800/80 bg-zinc-950/80 px-4 sm:px-8 backdrop-blur-xl">
          <div className="flex items-center gap-6">
            <Link href="/" className="transition-opacity hover:opacity-90">
              <MentorLogo size="md" subtitle="Autonomous Task & Schedule Intelligence" />
            </Link>
            <nav className="hidden sm:flex items-center gap-4 text-xs font-medium">
              <Link
                href="/"
                className="text-zinc-400 hover:text-white transition-colors"
              >
                Home
              </Link>
              <Link
                href="/team"
                className="text-indigo-400 font-semibold transition-colors"
              >
                Developer Team
              </Link>
            </nav>
          </div>

          <div className="flex items-center gap-3">
            <HealthStatusBadge />
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
            </Link>
          </div>
        </header>

        {/* Page Content Body */}
        <main className="flex flex-1 flex-col overflow-y-auto">
          <div className="flex-1 p-4 sm:p-6 lg:p-8 pb-safe">{children}</div>
          <footer className="border-t border-zinc-800/60 bg-zinc-950/70 px-6 py-4 text-center text-xs text-zinc-500 backdrop-blur-sm">
            <p>
              Built with care by{" "}
              <Link
                href="/team"
                className="font-medium text-indigo-400 hover:text-indigo-300 transition-colors underline-offset-4 hover:underline"
              >
                Code ArenaX
              </Link>
            </p>
          </footer>
        </main>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  const navGroups: NavGroup[] = [
    {
      title: "Workspace",
      items: [
        {
          href: "/dashboard",
          label: "Dashboard",
          icon: LayoutDashboard,
        },
        {
          href: "/tasks",
          label: "Tasks",
          icon: CheckSquare,
        },
        {
          href: "/schedule",
          label: "Schedule",
          icon: Clock,
        },
        {
          href: "/calendar",
          label: "Calendar",
          icon: Calendar,
        },
        {
          href: "/planner",
          label: "AI Planner",
          icon: Compass,
        },
      ],
    },
    {
      title: "Intelligence",
      items: [
        {
          href: "/copilot",
          label: "AI Copilot",
          icon: Sparkles,
        },
        {
          href: "/gmail",
          label: "Gmail",
          icon: Mail,
        },
        {
          href: "/actions",
          label: "Approvals & History",
          icon: ShieldAlert,
        },
      ],
    },
    {
      title: "System",
      items: [
        {
          href: "/settings/preferences",
          label: "Preferences",
          icon: Sliders,
        },
        {
          href: "/team",
          label: "Developer Team",
          icon: Users,
        },
      ],
    },
  ];

  // Helper to find current page label
  const allItems = navGroups.flatMap((g) => g.items);
  const currentItem = allItems.find(
    (item) => pathname === item.href || (item.href !== "/dashboard" && pathname.startsWith(`${item.href}/`))
  );

  return (
    <div className="flex min-h-screen bg-zinc-950 text-zinc-100 antialiased selection:bg-indigo-500 selection:text-white">
      {/* Desktop Sidebar */}
      <aside className="hidden w-64 flex-col border-r border-zinc-800/80 bg-zinc-950/90 backdrop-blur-xl md:flex shrink-0">
        {/* Brand Header */}
        <div className="flex h-16 items-center border-b border-zinc-800/80 px-5">
          <Link href="/dashboard" className="transition-opacity hover:opacity-90">
            <MentorLogo size="md" subtitle="Autonomous Copilot" />
          </Link>
        </div>

        {/* Grouped Navigation */}
        <nav className="flex-1 space-y-6 overflow-y-auto px-3.5 py-5 scrollbar-thin">
          {navGroups.map((group) => (
            <div key={group.title} className="space-y-1">
              <span className="px-3 text-[10px] font-bold uppercase tracking-wider text-zinc-500">
                {group.title}
              </span>
              <div className="mt-1.5 space-y-0.5">
                {group.items.map((item) => {
                  const isActive =
                    pathname === item.href ||
                    (item.href !== "/dashboard" && pathname.startsWith(`${item.href}/`));
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={`group flex items-center justify-between rounded-xl px-3 py-2 text-xs font-medium transition-all ${
                        isActive
                          ? "bg-indigo-600/15 text-indigo-300 border border-indigo-500/30 shadow-sm"
                          : "text-zinc-400 hover:bg-zinc-900/80 hover:text-zinc-100"
                      }`}
                    >
                      <div className="flex items-center gap-2.5">
                        <Icon
                          className={`h-4 w-4 shrink-0 transition-colors ${
                            isActive ? "text-indigo-400" : "text-zinc-500 group-hover:text-zinc-300"
                          }`}
                        />
                        <span>{item.label}</span>
                      </div>
                      {isActive && (
                        <div className="h-1.5 w-1.5 rounded-full bg-indigo-400 shadow-glow-indigo" />
                      )}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        {/* User Profile & Sign Out Footer */}
        <div className="border-t border-zinc-800/80 p-3 bg-zinc-950/60">
          <div className="flex items-center justify-between rounded-xl bg-zinc-900/70 p-2.5 border border-zinc-800/70">
            <div className="flex items-center gap-2.5 overflow-hidden">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-600/20 text-indigo-300 border border-indigo-500/30 font-semibold text-xs">
                {user?.email ? user.email.charAt(0).toUpperCase() : <UserIcon className="h-4 w-4" />}
              </div>
              <div className="truncate text-xs">
                <p className="truncate font-semibold text-zinc-200">
                  {user?.email || "Authenticated User"}
                </p>
                <p className="text-[10px] text-zinc-500">Active Workspace</p>
              </div>
            </div>
            <button
              onClick={logout}
              title="Sign Out"
              className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-rose-400 transition-colors"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top Header */}
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-zinc-800/80 bg-zinc-950/80 px-4 backdrop-blur-xl sm:px-6">
          <div className="flex items-center gap-3">
            {/* Mobile menu toggle */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="rounded-xl border border-zinc-800 p-2 text-zinc-400 hover:text-white md:hidden hover:bg-zinc-900 transition-colors"
              aria-label="Toggle navigation menu"
            >
              {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>

            {/* Mobile Brand Mark */}
            <div className="md:hidden">
              <MentorLogo size="sm" showWordmark={true} />
            </div>

            {/* Desktop Breadcrumb Navigation */}
            <div className="hidden md:flex items-center gap-2 text-xs">
              <span className="text-zinc-500 font-medium">Workspace</span>
              <ChevronRight className="h-3 w-3 text-zinc-600" />
              <span className="font-semibold text-zinc-200">
                {currentItem?.label || "Overview"}
              </span>
            </div>
          </div>

          {/* Header Controls & Status Badges */}
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={() => setCopilotOpen(true)}
              className="hidden sm:inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-indigo-700 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:from-indigo-500 hover:to-indigo-600 transition-all border border-indigo-400/30"
              title="Ask Mentor AI Copilot (Cmd+K)"
            >
              <Sparkles className="h-3.5 w-3.5 text-indigo-200" />
              <span>Ask Mentor</span>
              <kbd className="hidden lg:inline-block rounded bg-indigo-900/60 px-1 py-0.2 text-[9px] font-mono text-indigo-300">
                ⌘K
              </kbd>
            </button>

            <NotificationBell />
            <HealthStatusBadge />
          </div>
        </header>

        {/* Mobile Navigation Drawer */}
        {mobileMenuOpen && (
          <div className="fixed inset-0 top-16 z-30 flex flex-col bg-zinc-950/95 backdrop-blur-2xl border-b border-zinc-800 p-4 md:hidden animate-in fade-in duration-200">
            <nav className="flex-1 space-y-6 overflow-y-auto">
              {navGroups.map((group) => (
                <div key={group.title} className="space-y-1">
                  <span className="px-3 text-[10px] font-bold uppercase tracking-wider text-zinc-500">
                    {group.title}
                  </span>
                  <div className="mt-1 space-y-1">
                    {group.items.map((item) => {
                      const isActive =
                        pathname === item.href ||
                        (item.href !== "/dashboard" && pathname.startsWith(`${item.href}/`));
                      const Icon = item.icon;
                      return (
                        <Link
                          key={item.href}
                          href={item.href}
                          onClick={() => setMobileMenuOpen(false)}
                          className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium ${
                            isActive
                              ? "bg-indigo-600/20 text-indigo-300 border border-indigo-500/30"
                              : "text-zinc-400 hover:bg-zinc-900 hover:text-white"
                          }`}
                        >
                          <Icon className="h-4 w-4" />
                          <span>{item.label}</span>
                        </Link>
                      );
                    })}
                  </div>
                </div>
              ))}
            </nav>

            <div className="mt-auto border-t border-zinc-800 pt-4 flex items-center justify-between">
              <span className="text-xs text-zinc-400 truncate max-w-[200px]">
                {user?.email}
              </span>
              <button
                onClick={logout}
                className="flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-semibold text-rose-400 hover:bg-rose-500/10 transition-colors"
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
        <main className="flex flex-1 flex-col overflow-y-auto">
          <div className="flex-1 p-4 sm:p-6 lg:p-8 pb-safe">{children}</div>
          <footer className="border-t border-zinc-800/60 bg-zinc-950/70 px-6 py-4 text-center text-xs text-zinc-500 backdrop-blur-sm">
            <p>
              Built with care by{" "}
              <Link
                href="/team"
                className="font-medium text-indigo-400 hover:text-indigo-300 transition-colors underline-offset-4 hover:underline"
              >
                Code ArenaX
              </Link>
            </p>
          </footer>
        </main>

        {/* Persistent Floating Copilot Trigger */}
        <button
          type="button"
          onClick={() => setCopilotOpen(true)}
          className="fixed bottom-6 right-6 z-30 flex h-13 w-13 items-center justify-center rounded-2xl bg-gradient-to-tr from-indigo-600 via-indigo-600 to-purple-600 text-white shadow-xl hover:scale-105 active:scale-95 transition-all ring-1 ring-white/20 hover:shadow-indigo-500/40 p-3"
          aria-label="Open Mentor AI Copilot"
          title="Ask Mentor Copilot (Cmd+K)"
        >
          <Sparkles className="h-6 w-6 text-indigo-100" />
        </button>

        {/* Global Copilot Drawer */}
        <CopilotDrawer
          isOpen={copilotOpen}
          onClose={() => setCopilotOpen(false)}
        />
      </div>
    </div>
  );
}
