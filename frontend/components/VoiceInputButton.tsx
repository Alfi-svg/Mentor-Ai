"use client";

import React, { useEffect, useRef, useState } from "react";
import { AlertCircle, Mic, MicOff, Volume2 } from "lucide-react";

interface VoiceInputButtonProps {
  onTranscriptReady: (transcript: string) => void;
  disabled?: boolean;
}

type VoiceState = "idle" | "requesting" | "listening" | "error" | "unsupported";

// Extend Window interface for Web Speech API
interface SpeechRecognitionEvent extends Event {
  results: {
    [index: number]: {
      [index: number]: {
        transcript: string;
      };
      isFinal: boolean;
      length: number;
    };
    length: number;
  };
}

interface SpeechRecognitionErrorEvent extends Event {
  error: string;
}

interface ISpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onstart: (event: Event) => void;
  onresult: (event: SpeechRecognitionEvent) => void;
  onerror: (event: SpeechRecognitionErrorEvent) => void;
  onend: (event: Event) => void;
}

export function VoiceInputButton({ onTranscriptReady, disabled = false }: VoiceInputButtonProps) {
  const [state, setState] = useState<VoiceState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [interimText, setInterimText] = useState("");
  const recognitionRef = useRef<ISpeechRecognition | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;

    // Check Web Speech API support
    const SpeechRecognitionClass =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognitionClass) {
      setState("unsupported");
      return;
    }

    try {
      const recognition: ISpeechRecognition = new SpeechRecognitionClass();
      recognition.continuous = false; // Never record indefinitely in background
      recognition.interimResults = true; // Show live interim preview
      recognition.lang = "en-US";

      recognition.onstart = () => {
        setState("listening");
        setErrorMessage(null);
        setInterimText("");
      };

      recognition.onresult = (event: SpeechRecognitionEvent) => {
        let interim = "";
        let final = "";

        for (let i = 0; i < event.results.length; i++) {
          const item = event.results[i];
          const text = item[0].transcript;
          if (item.isFinal) {
            final += text + " ";
          } else {
            interim += text;
          }
        }

        if (interim) {
          setInterimText(interim);
        }

        if (final.trim()) {
          onTranscriptReady(final.trim());
          setInterimText("");
        }
      };

      recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
        console.warn("Speech recognition error:", event.error);
        if (event.error === "not-allowed") {
          setErrorMessage("Microphone permission was denied. Please allow microphone access in your browser settings.");
        } else if (event.error === "no-speech") {
          setErrorMessage("No speech detected. Please speak clearly into your microphone.");
        } else if (event.error === "network") {
          setErrorMessage("Network error during speech recognition.");
        } else {
          setErrorMessage(`Speech recognition error: ${event.error}`);
        }
        setState("error");
      };

      recognition.onend = () => {
        setState("idle");
        setInterimText("");
      };

      recognitionRef.current = recognition;
    } catch (err) {
      console.warn("Failed to initialize speech recognition:", err);
      setState("unsupported");
    }

    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {
          // ignore cleanup abort
        }
      }
    };
  }, [onTranscriptReady]);

  const toggleRecording = () => {
    if (disabled) return;

    if (state === "listening") {
      try {
        recognitionRef.current?.stop();
      } catch {
        setState("idle");
      }
      return;
    }

    if (state === "unsupported") {
      alert("Voice input is not supported by your current browser. Please use Chrome, Edge, or Safari, or enter instructions via text.");
      return;
    }

    setErrorMessage(null);
    setState("requesting");

    try {
      recognitionRef.current?.start();
    } catch (err) {
      console.warn("Could not start speech recognition:", err);
      setState("error");
      setErrorMessage("Could not access microphone.");
    }
  };

  return (
    <div className="relative inline-flex items-center">
      <button
        type="button"
        onClick={toggleRecording}
        disabled={disabled || state === "unsupported"}
        aria-label={state === "listening" ? "Stop voice input" : "Start voice input"}
        title={
          state === "unsupported"
            ? "Voice input is not supported by your browser. Use text input instead."
            : state === "listening"
            ? "Click to stop recording"
            : "Click to speak your plan"
        }
        className={`relative inline-flex items-center justify-center rounded-lg p-2 text-xs font-medium transition-all ${
          state === "listening"
            ? "bg-red-500/20 text-red-400 ring-2 ring-red-500 animate-pulse"
            : state === "unsupported"
            ? "cursor-not-allowed bg-zinc-800/40 text-zinc-600"
            : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700 hover:text-white"
        }`}
      >
        {state === "listening" ? (
          <Mic className="h-4 w-4 text-red-400" />
        ) : state === "unsupported" ? (
          <MicOff className="h-4 w-4" />
        ) : (
          <Mic className="h-4 w-4" />
        )}
      </button>

      {/* Listening Waveform Indicator Banner */}
      {state === "listening" && (
        <div className="absolute bottom-full mb-2 left-0 z-50 flex items-center gap-2 whitespace-nowrap rounded-lg border border-red-500/30 bg-zinc-900/95 px-3 py-1.5 shadow-xl text-xs text-red-400 backdrop-blur-md">
          <span className="flex h-2 w-2 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
          </span>
          <span className="font-semibold">Listening...</span>
          {interimText && (
            <span className="text-zinc-300 italic max-w-xs truncate">
              &ldquo;{interimText}&rdquo;
            </span>
          )}
          <span className="text-[10px] text-zinc-500">(Click mic to stop)</span>
        </div>
      )}

      {/* Error Message Tooltip */}
      {state === "error" && errorMessage && (
        <div className="absolute bottom-full mb-2 left-0 z-50 flex items-center gap-2 rounded-lg border border-red-500/30 bg-zinc-900/95 p-2 shadow-xl text-xs text-red-400 backdrop-blur-md max-w-xs">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          <span>{errorMessage}</span>
          <button
            onClick={() => setState("idle")}
            className="ml-auto text-[10px] text-zinc-400 hover:text-white"
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
}
