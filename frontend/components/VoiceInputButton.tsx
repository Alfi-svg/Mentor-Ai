"use client";

import React, { useEffect, useRef, useState } from "react";
import { AlertCircle, Check, Loader2, Mic, MicOff, Square, X } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { detectSupportedAudioMime, stopAllMediaTracks } from "@/lib/audio-recorder";

interface VoiceInputButtonProps {
  onTranscriptReady: (transcript: string) => void;
  disabled?: boolean;
}

type VoiceState = "idle" | "requesting" | "recording" | "transcribing" | "error";

export function VoiceInputButton({ onTranscriptReady, disabled = false }: VoiceInputButtonProps) {
  const [state, setState] = useState<VoiceState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [recordingSeconds, setRecordingSeconds] = useState(0);

  const mediaStreamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<any>(null);
  const isStartingRef = useRef(false);

  // Clean up on component unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        try {
          mediaRecorderRef.current.stop();
        } catch {
          // ignore
        }
      }
      stopAllMediaTracks(mediaStreamRef.current);
      mediaStreamRef.current = null;
    };
  }, []);

  const stopRecording = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // ignore
      }
    }
  };

  const cancelRecording = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    audioChunksRef.current = [];
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      try {
        mediaRecorderRef.current.ondataavailable = null;
        mediaRecorderRef.current.onstop = null;
        mediaRecorderRef.current.stop();
      } catch {
        // ignore
      }
    }
    stopAllMediaTracks(mediaStreamRef.current);
    mediaStreamRef.current = null;
    setState("idle");
    setRecordingSeconds(0);
  };

  const startRecording = async () => {
    if (disabled || isStartingRef.current || (state !== "idle" && state !== "error")) {
      return;
    }

    isStartingRef.current = true;
    setErrorMessage(null);
    setState("requesting");
    setRecordingSeconds(0);

    // Verify browser support for mediaDevices
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      isStartingRef.current = false;
      setState("error");
      setErrorMessage("Microphone access is not supported by your browser or connection is not secure (HTTPS).");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      mediaStreamRef.current = stream;
      audioChunksRef.current = [];

      const supported = detectSupportedAudioMime();
      let recorder: MediaRecorder;
      try {
        recorder = supported.mimeType
          ? new MediaRecorder(stream, { mimeType: supported.mimeType })
          : new MediaRecorder(stream);
      } catch {
        recorder = new MediaRecorder(stream);
      }

      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        stopAllMediaTracks(mediaStreamRef.current);
        mediaStreamRef.current = null;

        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }

        const rawMime = recorder.mimeType || supported.mimeType || "audio/webm";
        const actualMime = rawMime.split(";")[0].trim().toLowerCase();
        let ext = supported.extension;
        if (actualMime.includes("mp4")) ext = "mp4";
        else if (actualMime.includes("aac")) ext = "aac";
        else if (actualMime.includes("ogg")) ext = "ogg";
        else if (actualMime.includes("wav")) ext = "wav";

        const audioBlob = new Blob(audioChunksRef.current, { type: actualMime });

        if (audioBlob.size < 64) {
          setState("idle");
          setErrorMessage("Audio recording is empty or too short. Please speak clearly into your microphone.");
          return;
        }

        setState("transcribing");
        try {
          const res = await apiClient.copilot.transcribeAudio(audioBlob, `speech.${ext}`);
          if (res.transcript && res.transcript.trim()) {
            onTranscriptReady(res.transcript.trim());
            setState("idle");
          } else {
            setState("error");
            setErrorMessage("No clear speech was recognized. Please speak clearly and try again.");
          }
        } catch (transcribeErr: any) {
          setState("error");
          setErrorMessage(transcribeErr?.message || "Gemini speech transcription failed. Please try again.");
        }
      };

      recorder.onerror = () => {
        stopAllMediaTracks(mediaStreamRef.current);
        mediaStreamRef.current = null;
        setState("error");
        setErrorMessage("Microphone recording error occurred. Please try again.");
      };

      recorder.start(250); // Slice chunks every 250ms for reliable capture
      setState("recording");

      // Start 60-second timer with auto-stop
      let elapsed = 0;
      timerRef.current = setInterval(() => {
        elapsed += 1;
        setRecordingSeconds(elapsed);
        if (elapsed >= 60) {
          stopRecording();
        }
      }, 1000);
    } catch (err: any) {
      stopAllMediaTracks(mediaStreamRef.current);
      mediaStreamRef.current = null;
      setState("error");
      if (err?.name === "NotAllowedError" || err?.name === "PermissionDeniedError") {
        setErrorMessage("Microphone permission denied. Please allow microphone access in your browser settings.");
      } else if (err?.name === "NotFoundError" || err?.name === "DevicesNotFoundError") {
        setErrorMessage("No microphone detected. Please connect an audio input device.");
      } else {
        setErrorMessage(err?.message || "Could not access microphone.");
      }
    } finally {
      isStartingRef.current = false;
    }
  };

  const formatSeconds = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const s = sec % 60;
    return `${mins}:${s < 10 ? "0" : ""}${s}`;
  };

  return (
    <div className="relative inline-flex items-center">
      {state === "recording" ? (
        <div className="flex items-center gap-1.5 rounded-xl border border-red-500/40 bg-red-950/40 px-2.5 py-1 text-xs text-red-300 shadow-sm">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-red-500" />
          </span>
          <span className="font-mono text-[11px] font-semibold">{formatSeconds(recordingSeconds)} / 1:00</span>
          <button
            type="button"
            onClick={stopRecording}
            aria-label="Stop recording and transcribe"
            title="Stop recording"
            className="inline-flex items-center gap-1 rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-bold text-white hover:bg-red-500 transition-all"
          >
            <Square className="h-2.5 w-2.5 fill-current" />
            <span>Done</span>
          </button>
          <button
            type="button"
            onClick={cancelRecording}
            aria-label="Cancel recording"
            title="Cancel"
            className="rounded p-0.5 text-zinc-400 hover:text-white transition-all"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      ) : state === "transcribing" ? (
        <div className="flex items-center gap-1.5 rounded-xl border border-indigo-500/30 bg-indigo-950/40 px-2.5 py-1 text-xs text-indigo-300">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400" />
          <span className="text-[11px] font-medium">Transcribing with Gemini...</span>
        </div>
      ) : (
        <button
          type="button"
          onClick={startRecording}
          disabled={disabled || state === "requesting"}
          aria-label="Speak your plan"
          title="Click to speak your plan using Gemini voice input"
          className="relative inline-flex items-center gap-1.5 rounded-xl border border-zinc-700/80 bg-zinc-800/80 px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-zinc-700 hover:text-white transition-all disabled:opacity-50"
        >
          {state === "requesting" ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin text-brand-400" />
              <span className="text-[11px]">Requesting mic...</span>
            </>
          ) : (
            <>
              <Mic className="h-3.5 w-3.5 text-brand-400" />
              <span className="text-[11px]">Voice Input</span>
            </>
          )}
        </button>
      )}

      {/* Error Tooltip Banner */}
      {state === "error" && errorMessage && (
        <div className="absolute bottom-full mb-2 left-0 z-50 flex items-center gap-2 rounded-xl border border-rose-500/40 bg-zinc-950/95 p-2.5 shadow-2xl text-xs text-rose-300 backdrop-blur-md max-w-xs animate-in fade-in">
          <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
          <span className="text-[11px] leading-tight">{errorMessage}</span>
          <button
            type="button"
            onClick={() => setState("idle")}
            className="ml-auto rounded px-1 text-[10px] text-zinc-400 hover:text-white"
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
}
