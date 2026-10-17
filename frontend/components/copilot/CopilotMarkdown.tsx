"use client";

import React, { useState } from "react";
import { Check, Copy, Code2, AlertCircle, Info, Sparkles, Terminal } from "lucide-react";

interface CopilotMarkdownProps {
  content: string;
  className?: string;
}

/**
 * Escapes unsafe characters to prevent XSS injection.
 */
function sanitizeText(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * Validates that a link URL uses safe protocols.
 */
function isSafeUrl(url: string): boolean {
  const trimmed = url.trim().toLowerCase();
  return (
    trimmed.startsWith("https://") ||
    trimmed.startsWith("http://") ||
    trimmed.startsWith("/") ||
    trimmed.startsWith("#")
  );
}

/**
 * Code Block Component with Language Badge and One-Click Copy.
 */
function CodeBlock({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback if clipboard API is restricted
      const textarea = document.createElement("textarea");
      textarea.value = code;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const lineCount = code.split("\n").length;

  return (
    <div className="my-3 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950/95 shadow-md">
      <div className="flex items-center justify-between border-b border-zinc-800/80 bg-zinc-900/90 px-3.5 py-1.5 text-xs text-zinc-400">
        <div className="flex items-center gap-1.5 font-mono text-[11px] font-semibold text-zinc-300 uppercase tracking-wider">
          <Terminal className="h-3.5 w-3.5 text-indigo-400" />
          <span>{language || "code"}</span>
          <span className="text-[10px] text-zinc-500 font-normal">
            ({lineCount} {lineCount === 1 ? "line" : "lines"})
          </span>
        </div>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 rounded-lg px-2 py-0.5 text-[11px] text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 transition-colors"
          title="Copy code to clipboard"
        >
          {copied ? (
            <>
              <Check className="h-3 w-3 text-emerald-400" />
              <span className="text-emerald-400 font-medium">Copied!</span>
            </>
          ) : (
            <>
              <Copy className="h-3 w-3" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <pre className="overflow-x-auto p-3.5 font-mono text-xs leading-relaxed text-zinc-200 scrollbar-thin scrollbar-thumb-zinc-700">
        <code>{code}</code>
      </pre>
    </div>
  );
}

/**
 * Renders inline text elements: bold, italic, inline code, and safe links.
 */
function renderInline(text: string): React.ReactNode[] {
  // Regex parsing: inline code `...`, bold **...**, italic *...* or _..._, links [text](url)
  const tokens: React.ReactNode[] = [];
  const regex = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|_[^_]+_|\[[^\]]+\]\([^)]+\))/g;

  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      tokens.push(text.slice(lastIndex, match.index));
    }

    const token = match[0];

    if (token.startsWith("`") && token.endsWith("`")) {
      // Inline code
      const code = token.slice(1, -1);
      tokens.push(
        <code
          key={`code-${match.index}`}
          className="rounded-md bg-zinc-800/90 px-1.5 py-0.5 font-mono text-[11px] sm:text-xs text-indigo-300 border border-zinc-700/60 shadow-xs"
        >
          {code}
        </code>
      );
    } else if (token.startsWith("**") && token.endsWith("**")) {
      // Bold - high contrast readable white
      const boldText = token.slice(2, -2);
      tokens.push(
        <strong key={`bold-${match.index}`} className="font-semibold text-white drop-shadow-xs">
          {renderInline(boldText)}
        </strong>
      );
    } else if (
      (token.startsWith("*") && token.endsWith("*")) ||
      (token.startsWith("_") && token.endsWith("_"))
    ) {
      // Italic
      const italicText = token.slice(1, -1);
      tokens.push(
        <em key={`italic-${match.index}`} className="italic text-zinc-300">
          {renderInline(italicText)}
        </em>
      );
    } else if (token.startsWith("[") && token.includes("](") && token.endsWith(")")) {
      // Link [label](url)
      const linkMatch = token.match(/^\[(.*?)\]\((.*?)\)$/);
      if (linkMatch) {
        const [, label, rawUrl] = linkMatch;
        const safeUrl = isSafeUrl(rawUrl) ? rawUrl : "#";
        tokens.push(
          <a
            key={`link-${match.index}`}
            href={safeUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-400 hover:text-indigo-300 underline font-medium transition-colors"
          >
            {label}
          </a>
        );
      } else {
        tokens.push(token);
      }
    } else {
      tokens.push(token);
    }

    lastIndex = regex.lastIndex;
  }

  if (lastIndex < text.length) {
    tokens.push(text.slice(lastIndex));
  }

  return tokens;
}

/**
 * ChatGPT-Style Structured Markdown Renderer with Colorful Hierarchy for Copilot Responses.
 */
export function CopilotMarkdown({ content, className = "" }: CopilotMarkdownProps) {
  if (!content) return null;

  // Split into lines while preserving fenced code blocks
  const lines = content.split("\n");
  const elements: React.ReactNode[] = [];

  let inCodeBlock = false;
  let codeBuffer: string[] = [];
  let codeLanguage = "";

  let listBuffer: { type: "ul" | "ol"; items: string[] } | null = null;
  let tableBuffer: string[] = [];

  const flushList = () => {
    if (!listBuffer) return;
    const { type, items } = listBuffer;
    const ListTag = type === "ol" ? "ol" : "ul";
    const listClasses =
      type === "ol"
        ? "list-decimal list-outside pl-5 space-y-1.5 my-2.5 text-zinc-200 text-xs sm:text-sm"
        : "list-disc list-outside pl-5 space-y-1.5 my-2.5 text-zinc-200 text-xs sm:text-sm marker:text-indigo-400";

    elements.push(
      <ListTag key={`list-${elements.length}`} className={listClasses}>
        {items.map((item, idx) => (
          <li key={idx} className="leading-relaxed">
            {renderInline(item)}
          </li>
        ))}
      </ListTag>
    );
    listBuffer = null;
  };

  const flushTable = () => {
    if (tableBuffer.length === 0) return;
    const rows = tableBuffer
      .filter((line) => line.trim().startsWith("|") && line.trim().endsWith("|"))
      .map((line) =>
        line
          .trim()
          .slice(1, -1)
          .split("|")
          .map((c) => c.trim())
      );

    if (rows.length >= 2) {
      const headerRow = rows[0];
      const isSeparator = rows[1].every((c) => /^[-:]+$/.test(c));
      const bodyRows = isSeparator ? rows.slice(2) : rows.slice(1);

      elements.push(
        <div
          key={`table-${elements.length}`}
          className="my-3 overflow-x-auto rounded-xl border border-zinc-800 bg-zinc-950/70 shadow-sm"
        >
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-zinc-800 bg-zinc-900/90 text-indigo-200">
                {headerRow.map((h, i) => (
                  <th key={i} className="p-2.5 font-semibold tracking-wider">
                    {renderInline(h)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60 text-zinc-300">
              {bodyRows.map((row, rIdx) => (
                <tr key={rIdx} className="hover:bg-zinc-900/40 transition-colors">
                  {row.map((cell, cIdx) => (
                    <td key={cIdx} className="p-2.5 leading-normal">
                      {renderInline(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    tableBuffer = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // 1. Code Block Fence (```)
    if (trimmed.startsWith("```")) {
      if (inCodeBlock) {
        // End of code block
        elements.push(
          <CodeBlock
            key={`code-block-${elements.length}`}
            code={codeBuffer.join("\n")}
            language={codeLanguage}
          />
        );
        inCodeBlock = false;
        codeBuffer = [];
        codeLanguage = "";
      } else {
        // Flush any active lists or tables
        flushList();
        flushTable();
        inCodeBlock = true;
        codeLanguage = trimmed.slice(3).trim();
        codeBuffer = [];
      }
      continue;
    }

    if (inCodeBlock) {
      codeBuffer.push(line);
      continue;
    }

    // 2. Table Rows (| ... |)
    if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
      flushList();
      tableBuffer.push(line);
      continue;
    } else if (tableBuffer.length > 0) {
      flushTable();
    }

    // 3. Headings with Colorful Hierarchy (#, ##, ###, ####)
    if (trimmed.startsWith("# ")) {
      flushList();
      elements.push(
        <h1
          key={`h1-${elements.length}`}
          className="text-base sm:text-lg font-bold text-indigo-300 mt-4 mb-2 border-b border-indigo-500/20 pb-1 tracking-tight flex items-center gap-2"
        >
          {renderInline(trimmed.slice(2))}
        </h1>
      );
      continue;
    }
    if (trimmed.startsWith("## ")) {
      flushList();
      elements.push(
        <h2
          key={`h2-${elements.length}`}
          className="text-sm sm:text-base font-semibold text-sky-300 mt-3.5 mb-1.5 tracking-tight"
        >
          {renderInline(trimmed.slice(3))}
        </h2>
      );
      continue;
    }
    if (trimmed.startsWith("### ")) {
      flushList();
      elements.push(
        <h3
          key={`h3-${elements.length}`}
          className="text-xs sm:text-sm font-semibold text-violet-300 mt-3 mb-1 tracking-tight"
        >
          {renderInline(trimmed.slice(4))}
        </h3>
      );
      continue;
    }
    if (trimmed.startsWith("#### ")) {
      flushList();
      elements.push(
        <h4
          key={`h4-${elements.length}`}
          className="text-xs font-semibold text-zinc-300 mt-2.5 mb-1 uppercase tracking-wider"
        >
          {renderInline(trimmed.slice(5))}
        </h4>
      );
      continue;
    }

    // 4. GitHub Callouts & Blockquotes (> [!NOTE], > [!WARNING], >)
    if (trimmed.startsWith(">")) {
      flushList();
      const quoteBody = trimmed.replace(/^>+\s*/, "");
      let alertType: "note" | "warning" | "tip" | "standard" = "standard";

      if (quoteBody.startsWith("[!NOTE]") || quoteBody.startsWith("[!IMPORTANT]")) {
        alertType = "note";
      } else if (quoteBody.startsWith("[!WARNING]") || quoteBody.startsWith("[!CAUTION]")) {
        alertType = "warning";
      } else if (quoteBody.startsWith("[!TIP]")) {
        alertType = "tip";
      }

      if (alertType !== "standard") {
        const cleanedText = quoteBody.replace(/\[!(NOTE|IMPORTANT|WARNING|CAUTION|TIP)\]\s*/, "");
        const borderColor =
          alertType === "warning"
            ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
            : alertType === "tip"
            ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
            : "border-indigo-500/40 bg-indigo-500/10 text-indigo-200";

        const AlertIcon =
          alertType === "warning" ? AlertCircle : alertType === "tip" ? Sparkles : Info;

        elements.push(
          <div
            key={`alert-${elements.length}`}
            className={`my-2.5 rounded-xl border p-3 text-xs leading-relaxed flex items-start gap-2.5 ${borderColor}`}
          >
            <AlertIcon className="h-4 w-4 shrink-0 mt-0.5" />
            <div className="flex-1">{renderInline(cleanedText)}</div>
          </div>
        );
      } else {
        elements.push(
          <blockquote
            key={`quote-${elements.length}`}
            className="my-2 border-l-2 border-indigo-500/60 pl-3.5 italic text-zinc-400 text-xs sm:text-sm"
          >
            {renderInline(quoteBody)}
          </blockquote>
        );
      }
      continue;
    }

    // 5. Unordered List Items (- or *)
    const ulMatch = trimmed.match(/^[-*]\s+(.+)$/);
    if (ulMatch) {
      if (!listBuffer || listBuffer.type !== "ul") {
        flushList();
        listBuffer = { type: "ul", items: [] };
      }
      listBuffer.items.push(ulMatch[1]);
      continue;
    }

    // 6. Ordered List Items (1. 2. 3.)
    const olMatch = trimmed.match(/^(\d+)\.\s+(.+)$/);
    if (olMatch) {
      if (!listBuffer || listBuffer.type !== "ol") {
        flushList();
        listBuffer = { type: "ol", items: [] };
      }
      listBuffer.items.push(olMatch[2]);
      continue;
    }

    // Empty line separates blocks
    if (!trimmed) {
      flushList();
      flushTable();
      continue;
    }

    // 7. Regular Paragraph
    flushList();
    elements.push(
      <p
        key={`p-${elements.length}`}
        className="my-1.5 text-xs sm:text-sm leading-relaxed text-zinc-200"
      >
        {renderInline(trimmed)}
      </p>
    );
  }

  // Final flushes
  flushList();
  flushTable();
  if (inCodeBlock && codeBuffer.length > 0) {
    elements.push(
      <CodeBlock
        key={`code-block-${elements.length}`}
        code={codeBuffer.join("\n")}
        language={codeLanguage}
      />
    );
  }

  return (
    <div className={`copilot-markdown font-sans text-zinc-200 ${className}`}>
      {elements}
    </div>
  );
}
