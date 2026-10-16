"use client";

import React, { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowRight,
  BookOpen,
  Calendar,
  Check,
  CheckCircle2,
  Clock,
  Copy,
  ExternalLink,
  Flame,
  Mail,
  Mic,
  MicOff,
  Send,
  Sparkles,
  Volume2,
  VolumeX,
  X,
} from "lucide-react";
import { CopilotVoiceOrb, OrbState } from "./CopilotVoiceOrb";
import { apiClient } from "@/lib/api-client";
import {
  CopilotMessageRequest,
  CopilotResponse,
  CopilotScheduleSummary,
  EducationalResource,
  EmailDraftPreview,
  StudentAccountabilitySummary,
} from "@/lib/types";

interface ChatEntry {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: CopilotResponse;
  timestamp: string;
}

interface CopilotDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

export function CopilotDrawer({ isOpen, onClose }: CopilotDrawerProps) {
  const router = useRouter();

  // Assistant & Audio States
  const [orbState, setOrbState] = useState<OrbState>("idle");
  const [inputText, setInputText] = useState("");
  const [interimTranscript, setInterimTranscript] = useState("");
  const [isVoiceMuted, setIsVoiceMuted] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Email confirmation action loading
  const [emailSending, setEmailSending] = useState(false);
  const [emailSentResult, setEmailSentResult] = useState<string | null>(null);

  // Conversation history
  const [messages, setMessages] = useState<ChatEntry[]>([
    {
      id: "initial-welcome",
      role: "assistant",
      text: "Hello! I am Mentor, your educational copilot. Ask me about today's schedule, academic concepts, courses and lectures, or your academic deadlines.",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    },
  ]);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const recognitionRef = useRef<any>(null);
  const synthRef = useRef<SpeechSynthesis | null>(null);

  // Quick suggestion prompts
  const samplePrompts = [
    "Give me today's schedule",
    "Suggest a good Math 101 course",
    "Find a video explaining DFA",
    "Check my overdue tasks",
    "What is my study streak?",
  ];

  // Initialize Speech Synthesis and Speech Recognition
  useEffect(() => {
    if (typeof window === "undefined") return;

    if ("speechSynthesis" in window) {
      synthRef.current = window.speechSynthesis;
    }

    const SpeechRecognitionClass =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (SpeechRecognitionClass) {
      const recognition = new SpeechRecognitionClass();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = "en-US";

      recognition.onstart = () => {
        setOrbState("listening");
        setErrorMessage(null);
        setInterimTranscript("");
      };

      recognition.onresult = (event: any) => {
        let interim = "";
        let final = "";

        for (let i = 0; i < event.results.length; i++) {
          const res = event.results[i];
          const text = res[0].transcript;
          if (res.isFinal) {
            final += text + " ";
          } else {
            interim += text;
          }
        }

        if (interim) {
          setInterimTranscript(interim);
        }

        if (final.trim()) {
          setInputText(final.trim());
          setInterimTranscript("");
          // Automatically submit voice transcript
          handleSend(final.trim(), true);
        }
      };

      recognition.onerror = (event: any) => {
        console.warn("Speech recognition error:", event.error);
        if (event.error === "not-allowed") {
          setErrorMessage("Microphone access was denied. Please allow microphone permissions.");
        } else if (event.error === "no-speech") {
          setErrorMessage("No speech was detected. Please try speaking again.");
        } else {
          setErrorMessage(`Speech recognition error: ${event.error}`);
        }
        setOrbState("error");
      };

      recognition.onend = () => {
        if (orbState === "listening") {
          setOrbState("idle");
        }
        setInterimTranscript("");
      };

      recognitionRef.current = recognition;
    }

    return () => {
      stopSpeaking();
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {
          // Ignore cleanup error
        }
      }
    };
  }, []);

  // Scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, interimTranscript]);

  // Keyboard shortcut listener (Cmd+K / Ctrl+K)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (isOpen) {
          onClose();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const stopSpeaking = () => {
    if (synthRef.current) {
      synthRef.current.cancel();
      setIsSpeaking(false);
      if (orbState === "speaking") {
        setOrbState("idle");
      }
    }
  };

  const speakText = (text: string) => {
    if (isVoiceMuted || !synthRef.current) return;

    stopSpeaking();

    // Clean markdown syntax for speech
    const plainText = text
      .replace(/[*_#`[\]()]/g, "")
      .replace(/https?:\/\/\S+/g, "")
      .replace(/\n+/g, ". ");

    const utterance = new SpeechSynthesisUtterance(plainText);
    utterance.rate = 1.05;
    utterance.pitch = 1.0;

    utterance.onstart = () => {
      setIsSpeaking(true);
      setOrbState("speaking");
    };

    utterance.onend = () => {
      setIsSpeaking(false);
      setOrbState("idle");
    };

    utterance.onerror = () => {
      setIsSpeaking(false);
      setOrbState("idle");
    };

    synthRef.current.speak(utterance);
  };

  const toggleListening = () => {
    if (!recognitionRef.current) {
      alert("Speech recognition is not supported in this browser. Please use Chrome, Edge, or Safari, or enter instructions via text.");
      return;
    }

    if (orbState === "listening") {
      try {
        recognitionRef.current.stop();
      } catch {
        setOrbState("idle");
      }
      return;
    }

    stopSpeaking();
    setErrorMessage(null);
    setOrbState("listening");

    try {
      recognitionRef.current.start();
    } catch (err) {
      console.warn("Could not start speech recognition:", err);
      setOrbState("error");
      setErrorMessage("Could not access microphone.");
    }
  };

  const handleSend = async (messageToSend?: string, wasSpoken: boolean = false) => {
    const text = (messageToSend || inputText).trim();
    if (!text || loading) return;

    stopSpeaking();
    setInputText("");
    setLoading(true);
    setOrbState("thinking");
    setErrorMessage(null);

    const userEntry: ChatEntry = {
      id: `user-${Date.now()}`,
      role: "user",
      text: text,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };
    setMessages((prev) => [...prev, userEntry]);

    try {
      const clientTz =
        typeof Intl !== "undefined"
          ? Intl.DateTimeFormat().resolvedOptions().timeZone
          : "Asia/Dhaka";

      const payload: CopilotMessageRequest = {
        message: text,
        client_timezone: clientTz,
      };

      const response = await apiClient.copilot.sendMessage(payload);

      const assistantEntry: ChatEntry = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        text: response.reply,
        response: response,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };

      setMessages((prev) => [...prev, assistantEntry]);

      // If spoken or voice is active, speak the assistant's reply
      if (wasSpoken || orbState === "listening") {
        speakText(response.reply);
      } else {
        setOrbState("idle");
      }
    } catch (err: any) {
      console.error("Copilot request error:", err);
      setOrbState("error");
      setErrorMessage(err.message || "Failed to communicate with Mentor Copilot.");
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmSendEmail = async (draft: EmailDraftPreview) => {
    setEmailSending(true);
    setEmailSentResult(null);

    try {
      const res = await apiClient.copilot.confirmAction({
        action_type: "send_email",
        email_payload: {
          recipient_email: draft.recipient_email,
          subject: draft.subject,
          body: draft.body,
          thread_id: draft.thread_id || undefined,
        },
      });

      if (res.success) {
        setEmailSentResult("Email verified and sent successfully!");
        setMessages((prev) => [
          ...prev,
          {
            id: `system-${Date.now()}`,
            role: "assistant",
            text: `✓ ${res.result_message}`,
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          },
        ]);
      } else {
        setEmailSentResult(`Failed to send email: ${res.result_message}`);
      }
    } catch (err: any) {
      setEmailSentResult(`Error sending email: ${err.message}`);
    } finally {
      setEmailSending(false);
    }
  };

  const handleNavigate = (target?: { route: string; params?: Record<string, string> } | null) => {
    if (!target) return;
    const query = target.params
      ? new URLSearchParams(target.params).toString()
      : "";
    const url = query ? `${target.route}?${query}` : target.route;
    router.push(url);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative flex h-full w-full max-w-xl flex-col bg-zinc-950 border-l border-zinc-800 shadow-2xl">
        {/* Drawer Header */}
        <header className="flex h-16 items-center justify-between border-b border-zinc-800/80 px-6 bg-zinc-900/40">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600/20 border border-indigo-500/30 text-indigo-400">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-white tracking-tight">Mentor Copilot</h2>
              <p className="text-[10px] text-zinc-400 uppercase tracking-wider font-medium">
                {orbState === "listening"
                  ? "Listening to voice..."
                  : orbState === "thinking"
                  ? "Thinking & retrieving..."
                  : orbState === "speaking"
                  ? "Speaking response..."
                  : "Educational Assistant"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {isSpeaking && (
              <button
                onClick={stopSpeaking}
                className="flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 py-1 text-xs text-zinc-300 hover:text-white transition-colors"
                title="Stop speaking"
              >
                <VolumeX className="h-3.5 w-3.5 text-rose-400" />
                <span>Stop</span>
              </button>
            )}

            <button
              onClick={() => setIsVoiceMuted(!isVoiceMuted)}
              className="rounded-lg p-2 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 transition-colors"
              title={isVoiceMuted ? "Unmute voice response" : "Mute voice response"}
            >
              {isVoiceMuted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
            </button>

            <button
              onClick={onClose}
              className="rounded-lg p-2 text-zinc-400 hover:bg-zinc-800 hover:text-white transition-colors"
              aria-label="Close Copilot"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </header>

        {/* Central Siri/JARVIS Orb & Status Area */}
        <div className="flex flex-col items-center justify-center py-4 bg-gradient-to-b from-zinc-900/50 to-zinc-950 border-b border-zinc-800/60">
          <CopilotVoiceOrb
            state={orbState}
            size={130}
            onClick={toggleListening}
          />
          <p className="mt-2 text-xs font-medium text-zinc-400">
            {orbState === "listening"
              ? "Listening... (Click orb or mic to stop)"
              : orbState === "speaking"
              ? "Speaking..."
              : orbState === "thinking"
              ? "Synthesizing schedule & resources..."
              : "Click orb to speak or type below"}
          </p>

          {interimTranscript && (
            <div className="mt-2 px-4 py-1.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-xs text-indigo-300 italic max-w-sm truncate animate-pulse">
              &ldquo;{interimTranscript}&rdquo;
            </div>
          )}

          {errorMessage && (
            <div className="mt-2 flex items-center gap-2 rounded-lg bg-rose-500/10 border border-rose-500/20 px-3 py-1.5 text-xs text-rose-400 max-w-md">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}
        </div>

        {/* Conversation Message Stream */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-5">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}
            >
              <div
                className={`max-w-[90%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "bg-indigo-600 text-white rounded-br-none shadow-md"
                    : "bg-zinc-900 border border-zinc-800 text-zinc-200 rounded-bl-none shadow-sm"
                }`}
              >
                {/* Natural Response Text */}
                <div className="whitespace-pre-wrap">{msg.text}</div>

                {/* 1. Schedule Intelligence Card */}
                {msg.response?.schedule_summary && (
                  <div className="mt-3.5 rounded-xl border border-indigo-500/30 bg-zinc-950/80 p-3.5 shadow-inner">
                    <div className="flex items-center justify-between border-b border-zinc-800 pb-2 mb-2.5">
                      <div className="flex items-center gap-2 text-xs font-semibold text-indigo-400">
                        <Calendar className="h-3.5 w-3.5" />
                        <span>Schedule Overview ({msg.response.schedule_summary.target_date})</span>
                      </div>
                      <span className="text-[10px] text-zinc-500 font-mono">
                        {msg.response.schedule_summary.timezone}
                      </span>
                    </div>

                    <div className="space-y-1.5">
                      {msg.response.schedule_summary.scheduled_items.map((item) => (
                        <div
                          key={item.id}
                          className="flex items-center justify-between text-xs py-1 px-2 rounded bg-zinc-900/60"
                        >
                          <div className="flex items-center gap-2 truncate">
                            <span className="font-mono text-zinc-400 text-[11px] shrink-0">
                              {item.start_time}
                            </span>
                            <span className={`truncate font-medium ${item.is_completed ? "line-through text-zinc-500" : "text-zinc-200"}`}>
                              {item.title}
                            </span>
                          </div>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 shrink-0 capitalize">
                            {item.item_type.replace("_", " ")}
                          </span>
                        </div>
                      ))}

                      {msg.response.schedule_summary.deadlines.map((dl) => (
                        <div
                          key={dl.id}
                          className="flex items-center justify-between text-xs py-1 px-2 rounded bg-amber-500/10 border border-amber-500/20 text-amber-300"
                        >
                          <span className="truncate font-medium">{dl.title}</span>
                          <span className="text-[10px] font-mono">Due {dl.deadline_time}</span>
                        </div>
                      ))}
                    </div>

                    {msg.response.navigation && (
                      <button
                        onClick={() => handleNavigate(msg.response?.navigation)}
                        className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 transition-colors shadow-sm"
                      >
                        <span>{msg.response.navigation.label}</span>
                        <ArrowRight className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                )}

                {/* 2. Educational Resource Cards */}
                {msg.response?.resources && msg.response.resources.length > 0 && (
                  <div className="mt-3.5 space-y-2.5">
                    {msg.response.resources.map((res, i) => (
                      <div
                        key={i}
                        className="rounded-xl border border-zinc-800 bg-zinc-950/90 p-3 hover:border-zinc-700 transition-colors"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <span className="text-[10px] uppercase font-bold tracking-wider text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded-full">
                              {res.platform}
                            </span>
                            <h4 className="mt-1 text-xs font-semibold text-white">{res.title}</h4>
                          </div>
                          <a
                            href={res.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-1 text-[11px] font-medium text-indigo-400 hover:text-indigo-300 underline shrink-0"
                          >
                            <span>Open</span>
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        </div>
                        <p className="mt-1.5 text-xs text-zinc-400 leading-normal">{res.description}</p>
                        <p className="mt-1 text-[11px] text-zinc-500 italic">
                          Why: {res.why_recommended}
                        </p>
                      </div>
                    ))}
                  </div>
                )}

                {/* 3. Email Draft Preview Card (Safety Gated) */}
                {msg.response?.email_draft && (
                  <div className="mt-3.5 rounded-xl border border-amber-500/30 bg-zinc-950/95 p-3.5 shadow-lg">
                    <div className="flex items-center gap-2 border-b border-zinc-800 pb-2 mb-2 text-xs font-semibold text-amber-400">
                      <Mail className="h-3.5 w-3.5" />
                      <span>Email Draft Preview (Requires Confirmation)</span>
                    </div>

                    <div className="space-y-1.5 text-xs text-zinc-300">
                      <p>
                        <span className="text-zinc-500">To:</span>{" "}
                        <span className="font-mono text-zinc-200">
                          {msg.response.email_draft.recipient_name
                            ? `${msg.response.email_draft.recipient_name} <${msg.response.email_draft.recipient_email}>`
                            : msg.response.email_draft.recipient_email}
                        </span>
                      </p>
                      <p>
                        <span className="text-zinc-500">Subject:</span>{" "}
                        <span className="font-medium text-zinc-200">
                          {msg.response.email_draft.subject}
                        </span>
                      </p>
                      <div className="mt-2 rounded bg-zinc-900 p-2.5 font-sans whitespace-pre-wrap border border-zinc-800 text-zinc-300 text-xs leading-relaxed">
                        {msg.response.email_draft.body}
                      </div>
                    </div>

                    {emailSentResult ? (
                      <p className="mt-3 text-xs font-semibold text-emerald-400">{emailSentResult}</p>
                    ) : (
                      <div className="mt-3 flex items-center justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => setEmailSentResult("Draft discarded.")}
                          className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-400 hover:text-white"
                        >
                          Discard
                        </button>
                        <button
                          type="button"
                          onClick={() => handleConfirmSendEmail(msg.response!.email_draft!)}
                          disabled={emailSending}
                          className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 transition-colors disabled:opacity-50"
                        >
                          {emailSending ? "Sending..." : "Confirm & Send"}
                          <Send className="h-3 w-3" />
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {/* 4. Student Accountability Card */}
                {msg.response?.accountability && (
                  <div className="mt-3.5 rounded-xl border border-indigo-500/20 bg-zinc-950/80 p-3">
                    <div className="flex items-center gap-2 text-xs font-semibold text-indigo-400 mb-2">
                      <Flame className="h-4 w-4 text-amber-500" />
                      <span>Consistency & Progress</span>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-center text-xs">
                      <div className="rounded bg-zinc-900 p-2 border border-zinc-800">
                        <span className="block text-base font-bold text-amber-400">
                          {msg.response.accountability.streak_days}d
                        </span>
                        <span className="text-[10px] text-zinc-500">Streak</span>
                      </div>
                      <div className="rounded bg-zinc-900 p-2 border border-zinc-800">
                        <span className="block text-base font-bold text-emerald-400">
                          {msg.response.accountability.completed_today_count}
                        </span>
                        <span className="text-[10px] text-zinc-500">Completed</span>
                      </div>
                      <div className="rounded bg-zinc-900 p-2 border border-zinc-800">
                        <span className="block text-base font-bold text-rose-400">
                          {msg.response.accountability.missed_sessions_count}
                        </span>
                        <span className="text-[10px] text-zinc-500">Missed</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
              <span className="mt-1 text-[10px] text-zinc-500">{msg.timestamp}</span>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Quick Suggestion Prompts */}
        <div className="border-t border-zinc-800/80 bg-zinc-900/30 px-4 py-2.5 overflow-x-auto whitespace-nowrap scrollbar-none flex gap-2">
          {samplePrompts.map((p, i) => (
            <button
              key={i}
              type="button"
              onClick={() => handleSend(p)}
              disabled={loading}
              className="inline-flex items-center gap-1.5 rounded-full border border-zinc-800 bg-zinc-900/80 px-3 py-1 text-xs text-zinc-400 hover:border-indigo-500/40 hover:text-indigo-300 transition-colors"
            >
              <Sparkles className="h-3 w-3 text-indigo-400" />
              <span>{p}</span>
            </button>
          ))}
        </div>

        {/* Input Bar */}
        <div className="border-t border-zinc-800 bg-zinc-950 p-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex items-center gap-2"
          >
            {/* Voice Input Button */}
            <button
              type="button"
              onClick={toggleListening}
              className={`rounded-xl p-2.5 transition-all ${
                orbState === "listening"
                  ? "bg-rose-500/20 text-rose-400 ring-2 ring-rose-500 animate-pulse"
                  : "bg-zinc-900 text-zinc-400 hover:bg-zinc-800 hover:text-white border border-zinc-800"
              }`}
              title={orbState === "listening" ? "Stop listening" : "Speak to Mentor"}
            >
              {orbState === "listening" ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
            </button>

            {/* Text Input Field */}
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder="Ask Mentor about schedule, courses, DFA, code..."
              disabled={loading}
              className="flex-1 rounded-xl border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-sm text-zinc-200 placeholder-zinc-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />

            {/* Send Button */}
            <button
              type="submit"
              disabled={loading || !inputText.trim()}
              className="rounded-xl bg-indigo-600 p-2.5 text-white hover:bg-indigo-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
              title="Submit message"
            >
              <Send className="h-5 w-5" />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
