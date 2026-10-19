"use client";

import React from "react";
import { AuthProvider } from "@/lib/auth-context";
import { ToastProvider } from "@/components/ui/ToastProvider";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <ToastProvider>{children}</ToastProvider>
    </AuthProvider>
  );
}

