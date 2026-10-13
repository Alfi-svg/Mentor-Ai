"use client";

import React, { useEffect, useRef, useState } from "react";
import { AlertTriangle, Bell, Check, CheckCheck, Clock, ExternalLink } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { NotificationItem } from "@/lib/types";

export function NotificationBell() {
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const fetchNotifications = async () => {
    try {
      // First trigger evaluate to ensure all pending deadlines are caught
      await apiClient.evaluateNotifications().catch(() => {});
      const list = await apiClient.getNotifications(false);
      setNotifications(list);
      setUnreadCount(list.filter((n) => !n.is_read).length);
    } catch {
      // Silently handle if unauthenticated or network error
    }
  };

  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 60000); // Poll every minute
    return () => clearInterval(interval);
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleMarkAsRead = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await apiClient.markNotificationRead(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch {
      // ignore
    }
  };

  const handleMarkAllRead = async () => {
    setLoading(true);
    try {
      await apiClient.markAllNotificationsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  const formatScheduledTime = (timeStr: string) => {
    try {
      return new Date(timeStr).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return timeStr;
    }
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        aria-label="Open notifications"
        className="relative rounded-lg border border-zinc-800 bg-zinc-900/80 p-2 text-zinc-400 hover:text-white hover:border-zinc-700 transition-colors"
      >
        <Bell className="h-4 w-4" />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold text-white shadow-sm animate-pulse">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 sm:w-96 rounded-xl border border-zinc-800 bg-zinc-900 shadow-2xl z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-150">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3 bg-zinc-900/90">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-white">Notifications</span>
              {unreadCount > 0 && (
                <span className="rounded-full bg-rose-500/20 px-2 py-0.5 text-[10px] font-bold text-rose-300">
                  {unreadCount} unread
                </span>
              )}
            </div>
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={handleMarkAllRead}
                disabled={loading}
                className="flex items-center gap-1 text-[11px] font-medium text-brand-400 hover:text-brand-300 transition-colors"
              >
                <CheckCheck className="h-3 w-3" />
                <span>Mark all read</span>
              </button>
            )}
          </div>

          {/* List */}
          <div className="max-h-80 overflow-y-auto divide-y divide-zinc-800/60">
            {notifications.length === 0 ? (
              <div className="p-6 text-center text-xs text-zinc-500">
                <Bell className="mx-auto h-6 w-6 text-zinc-600 mb-2 stroke-[1.5]" />
                No deadline notifications yet.
              </div>
            ) : (
              notifications.map((notif) => {
                const isOverdue = notif.notification_type === "overdue";
                const isDueNow = notif.notification_type === "due_now";

                return (
                  <div
                    key={notif.id}
                    className={`p-3.5 flex items-start gap-3 transition-colors ${
                      notif.is_read
                        ? "bg-zinc-900/40 text-zinc-400"
                        : "bg-zinc-800/40 text-zinc-100"
                    }`}
                  >
                    <div className="mt-0.5 shrink-0">
                      {isOverdue ? (
                        <div className="rounded-full bg-rose-500/10 p-1 text-rose-400 border border-rose-500/20">
                          <AlertTriangle className="h-3.5 w-3.5" />
                        </div>
                      ) : isDueNow ? (
                        <div className="rounded-full bg-amber-500/10 p-1 text-amber-400 border border-amber-500/20">
                          <Clock className="h-3.5 w-3.5" />
                        </div>
                      ) : (
                        <div className="rounded-full bg-sky-500/10 p-1 text-sky-400 border border-sky-500/20">
                          <Clock className="h-3.5 w-3.5" />
                        </div>
                      )}
                    </div>

                    <div className="flex-1 space-y-1 overflow-hidden">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-xs font-semibold truncate text-white">
                          {notif.title}
                        </p>
                        <span className="text-[10px] text-zinc-400 font-mono shrink-0">
                          {formatScheduledTime(notif.scheduled_for)}
                        </span>
                      </div>
                      <p className="text-[11px] text-zinc-300 leading-snug">
                        {notif.message}
                      </p>
                    </div>

                    {!notif.is_read && (
                      <button
                        type="button"
                        onClick={(e) => handleMarkAsRead(notif.id, e)}
                        title="Mark as read"
                        className="rounded p-1 text-zinc-500 hover:text-emerald-400 hover:bg-zinc-800 transition-colors shrink-0"
                      >
                        <Check className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
