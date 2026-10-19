"use client";

import React from "react";
import { Modal } from "./Modal";
import { AlertTriangle, Info, HelpCircle, Loader2 } from "lucide-react";

export type ConfirmVariant = "danger" | "warning" | "primary";

export interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  description: React.ReactNode;
  confirmText?: string;
  cancelText?: string;
  variant?: ConfirmVariant;
  isLoading?: boolean;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
}

export function ConfirmDialog({
  isOpen,
  title,
  description,
  confirmText = "Confirm",
  cancelText = "Cancel",
  variant = "primary",
  isLoading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const getIcon = () => {
    switch (variant) {
      case "danger":
        return (
          <div className="w-10 h-10 rounded-full bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400 shrink-0">
            <AlertTriangle className="w-5 h-5" />
          </div>
        );
      case "warning":
        return (
          <div className="w-10 h-10 rounded-full bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400 shrink-0">
            <AlertTriangle className="w-5 h-5" />
          </div>
        );
      default:
        return (
          <div className="w-10 h-10 rounded-full bg-[#625BFF]/10 border border-[#625BFF]/20 flex items-center justify-center text-[#625BFF] shrink-0">
            <HelpCircle className="w-5 h-5" />
          </div>
        );
    }
  };

  const getConfirmButtonClasses = () => {
    switch (variant) {
      case "danger":
        return "bg-rose-600 hover:bg-rose-500 text-white shadow-lg shadow-rose-900/30 focus:ring-rose-500";
      case "warning":
        return "bg-amber-600 hover:bg-amber-500 text-white shadow-lg shadow-amber-900/30 focus:ring-amber-500";
      default:
        return "bg-[#625BFF] hover:bg-[#5248E5] text-white shadow-lg shadow-[#625BFF]/30 focus:ring-[#625BFF]";
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={isLoading ? () => {} : onCancel} maxWidth="md">
      <div className="flex gap-4 items-start">
        {getIcon()}
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-white tracking-tight">
            {title}
          </h3>
          <div className="text-sm text-slate-300 mt-2 leading-relaxed">
            {description}
          </div>
        </div>
      </div>

      <div className="mt-6 flex items-center justify-end gap-3 pt-4 border-t border-[#1e2f57]">
        <button
          type="button"
          onClick={onCancel}
          disabled={isLoading}
          className="px-4 py-2 text-sm font-medium text-slate-300 hover:text-white hover:bg-white/5 rounded-xl border border-slate-700/60 transition disabled:opacity-50"
        >
          {cancelText}
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={isLoading}
          className={`px-4 py-2 text-sm font-medium rounded-xl transition flex items-center gap-2 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-[#0d162e] disabled:opacity-50 ${getConfirmButtonClasses()}`}
        >
          {isLoading && <Loader2 className="w-4 h-4 animate-spin" />}
          <span>{confirmText}</span>
        </button>
      </div>
    </Modal>
  );
}
