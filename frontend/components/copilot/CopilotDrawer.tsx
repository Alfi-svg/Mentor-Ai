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
  ExternalLink,
  Flame,
  Mail,
  Mic,
  MicOff,
  Play,
  RotateCcw,
  Send,
  Settings,
  Sparkles,
  Volume2,
  VolumeX,
  X,
  Copy,
  MessageSquare,
  Square,
} from "lucide-react";
import { CopilotVoiceOrb, OrbState } from "./CopilotVoiceOrb";
import { CopilotMarkdown } from "./CopilotMarkdown";
import { apiClient } from "@/lib/api-client";
import { detectSupportedAudioMime, stopAllMediaTracks } from "@/lib/audio-recorder";
import {
  CopilotMessageRequest,
  CopilotPreferences,
  CopilotResponse,
  CopilotScheduleSummary,
  CopilotVoiceOption,
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

const DEFAULT_VOICES: CopilotVoiceOption[] = [
  {
    id: "masculine",
    name: "Masculine",
    perceived_sound: "masculine",
    description: "Natural, balanced masculine-sounding voice with clear articulation.",
    sample_text: "Hello! I am ready to review your schedule, master concepts, or draft email replies.",
  },
  {
    id: "feminine",
    name: "Feminine",
    perceived_sound: "feminine",
    description: "Natural, clear feminine-sounding voice with a warm, supportive tone.",
    sample_text: "Hello! I am Mentor, your educational copilot. How can I help with your studies today?",
  },
  {
    id: "deep_vocal",
    name: "Deep Vocal",
    perceived_sound: "masculine",
    description: "Lower-pitched, rich, authoritative vocal tone for deep focus.",
    sample_text: "Welcome back. Let us review your tasks and keep your study streak strong.",
  },
  {
    id: "natural_vocal",
    name: "Natural Vocal",
    perceived_sound: "feminine",
    description: "Distinct, conversational voice with a balanced and versatile tone.",
    sample_text: "Good morning! You have scheduled focus blocks and two academic deadlines today.",
  },
  {
    id: "nova",
    name: "Nova",
    perceived_sound: "feminine",
    description: "Warm, upbeat, and natural tone.",
    sample_text: "Hello! I am Mentor, your educational assistant. How can I help with your studies today?",
  },
  {
    id: "shimmer",
    name: "Shimmer",
    perceived_sound: "feminine",
    description: "Clear, expressive, and friendly tone.",
    sample_text: "Good morning! You have scheduled focus blocks and two academic deadlines today.",
  },
  {
    id: "echo",
    name: "Echo",
    perceived_sound: "masculine",
    description: "Resonant, deep, and conversational tone.",
    sample_text: "Hello! I am ready to review your schedule, master concepts, or draft email replies.",
  },
  {
    id: "onyx",
    name: "Onyx",
    perceived_sound: "masculine",
    description: "Calm, authoritative, and focused tone.",
    sample_text: "Welcome back. Let us review your tasks and keep your study streak strong.",
  },
];

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

  // Interaction Mode: "text" (silent, typed, Markdown) vs "voice" (spoken, Gemini STT & TTS)
  const [interactionMode, setInteractionMode] = useState<"text" | "voice">("text");
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);

  // Settings & Voice Preferences
  const [showSettings, setShowSettings] = useState(false);
  const [selectedVoice, setSelectedVoice] = useState<string>("nova");
  const [selectedGender, setSelectedGender] = useState<"masculine" | "feminine">("feminine");
  const [availableVoices, setAvailableVoices] = useState<CopilotVoiceOption[]>(DEFAULT_VOICES);
  const [previewingVoiceId, setPreviewingVoiceId] = useState<string | null>(null);
  const [reviewBeforeSend, setReviewBeforeSend] = useState<boolean>(true);
  const [transcriptNotice, setTranscriptNotice] = useState<string | null>(null);

  // Email confirmation action loading
  const [emailSending, setEmailSending] = useState(false);
  const [emailSentResult, setEmailSentResult] = useState<string | null>(null);

  // Recording via MediaRecorder (for Gemini multimodal audio STT)
  const [isRecordingMedia, setIsRecordingMedia] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const recordingTimerRef = useRef<any>(null);
  const isStartingRecordingRef = useRef<boolean>(false);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
  const textInputRef = useRef<HTMLInputElement | null>(null);

  // Conversation history
  const [messages, setMessages] = useState<ChatEntry[]>([
    {
      id: "initial-welcome",
      role: "assistant",
      text: "Hello! I am Mentor, your AI educational copilot. Ask me about your tasks, today's schedule, Google Calendar events, recent Gmail messages, or academic concepts in English, Bangla, or Banglish.",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    },
  ]);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const recognitionRef = useRef<any>(null);
  const synthRef = useRef<SpeechSynthesis | null>(null);

  // Quick suggestion prompts
  const samplePrompts = [
    "Brief me on my day",
    "What should I focus on first?",
    "amar ajker task ki ki?",
    "ajke amar ki ki event ache?",
    "notun mail ashche?",
    "Suggest a good Math 101 course",
    "Find a video explaining DFA",
    "What is my study streak?",
  ];

  // Load User Copilot Voice Preferences & Voice Options
  useEffect(() => {
    if (typeof window === "undefined") return;

    apiClient.copilot
      .getPreferences()
      .then((prefs) => {
        if (prefs?.voice_preset) {
          setSelectedVoice(prefs.voice_preset);
          setSelectedGender(prefs.voice_gender || "feminine");
        }
        if (typeof prefs?.review_before_send === "boolean") {
          setReviewBeforeSend(prefs.review_before_send);
        }
      })
      .catch((err) => {
        console.warn("Could not load Copilot voice preferences:", err);
      });

    apiClient.copilot
      .getVoices()
      .then((voices) => {
        if (voices && voices.length > 0) {
          setAvailableVoices(voices);
        }
      })
      .catch(() => {
        // Fall back to DEFAULT_VOICES
      });
  }, []);

  // Initialize Speech Synthesis and Web Speech Recognition fallback
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
          handleSend(final.trim(), true);
        }
      };

      recognition.onerror = (event: any) => {
        if (event.error === "not-allowed") {
          setErrorMessage("Microphone access was denied. Please allow microphone permissions.");
        } else if (event.error === "no-speech") {
          setErrorMessage("No speech was detected. Please try speaking again.");
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
      if (recordingTimerRef.current) {
        clearInterval(recordingTimerRef.current);
        recordingTimerRef.current = null;
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
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
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {
          // Ignore cleanup error
        }
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, interimTranscript]);

  const stopSpeaking = () => {
    // 1. Stop HTML5 audio player
    if (audioPlayerRef.current) {
      audioPlayerRef.current.pause();
      audioPlayerRef.current.currentTime = 0;
      audioPlayerRef.current = null;
    }
    // 2. Stop browser speech synthesis
    if (synthRef.current) {
      synthRef.current.cancel();
    }
    setIsSpeaking(false);
    if (orbState === "speaking") {
      setOrbState("idle");
    }
    setPreviewingVoiceId(null);
  };

  const stopListening = () => {
    if (recordingTimerRef.current) {
      clearInterval(recordingTimerRef.current);
      recordingTimerRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // ignore
      }
    }
  };

  const cancelListening = () => {
    if (recordingTimerRef.current) {
      clearInterval(recordingTimerRef.current);
      recordingTimerRef.current = null;
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
    setIsRecordingMedia(false);
    setOrbState("idle");
    setRecordingSeconds(0);
  };

  const handleSwitchMode = (mode: "text" | "voice") => {
    stopSpeaking();
    if (isRecordingMedia) {
      cancelListening();
    }
    setInteractionMode(mode);
    setErrorMessage(null);
    if (mode === "text") {
      setTranscriptNotice(null);
    }
  };

  const copyFullMessage = async (msgId: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedMessageId(msgId);
      setTimeout(() => setCopiedMessageId(null), 2000);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setCopiedMessageId(msgId);
      setTimeout(() => setCopiedMessageId(null), 2000);
    }
  };

  const playSynthesizedAudio = (base64Audio: string, mimeType = "audio/mpeg") => {
    if (isVoiceMuted) return;
    stopSpeaking();

    try {
      const audioUrl = `data:${mimeType};base64,${base64Audio}`;
      const audio = new Audio(audioUrl);
      audioPlayerRef.current = audio;

      audio.onplay = () => {
        setIsSpeaking(true);
        setOrbState("speaking");
      };

      audio.onended = () => {
        setIsSpeaking(false);
        setOrbState("idle");
        audioPlayerRef.current = null;
      };

      audio.onerror = (e) => {
        console.warn("Audio element error during playback:", e);
        setIsSpeaking(false);
        setOrbState("idle");
      };

      audio.play().catch((err) => {
        console.warn("Audio autoplay blocked or failed:", err);
        setIsSpeaking(false);
        setOrbState("idle");
      });
    } catch (err) {
      console.warn("Could not play synthesized audio:", err);
      setIsSpeaking(false);
      setOrbState("idle");
    }
  };

  const speakTextFallback = (text: string, voiceId?: string) => {
    if (isVoiceMuted || !synthRef.current) return;
    stopSpeaking();

    const plainText = text
      .replace(/[*_#`[\]()]/g, "")
      .replace(/https?:\/\/\S+/g, "")
      .replace(/\n+/g, ". ");

    const utterance = new SpeechSynthesisUtterance(plainText);
    const activeVoicePreset = (voiceId || selectedVoice).toLowerCase();

    // Map acoustic pitch and rate based on selected voice preset
    if (activeVoicePreset === "deep_vocal" || activeVoicePreset === "onyx") {
      utterance.pitch = 0.75; // noticeably lower, deeper vocal tone
      utterance.rate = 0.95;
    } else if (activeVoicePreset === "feminine" || activeVoicePreset === "nova") {
      utterance.pitch = 1.05;
      utterance.rate = 1.0;
    } else if (activeVoicePreset === "masculine" || activeVoicePreset === "echo") {
      utterance.pitch = 1.0;
      utterance.rate = 1.0;
    } else {
      // natural_vocal / shimmer / alloy
      utterance.pitch = 1.0;
      utterance.rate = 1.0;
    }

    // Try to find matching system voice if loaded
    const systemVoices = synthRef.current.getVoices?.() || [];
    if (systemVoices.length > 0) {
      if (activeVoicePreset === "feminine" || activeVoicePreset === "nova" || activeVoicePreset === "shimmer") {
        const femaleVoice = systemVoices.find((v) =>
          /female|woman|samantha|victoria|zira|karen/i.test(v.name)
        );
        if (femaleVoice) utterance.voice = femaleVoice;
      } else if (activeVoicePreset === "masculine" || activeVoicePreset === "echo" || activeVoicePreset === "deep_vocal" || activeVoicePreset === "onyx") {
        const maleVoice = systemVoices.find((v) =>
          /male|man|daniel|alex|david|george/i.test(v.name)
        );
        if (maleVoice) utterance.voice = maleVoice;
      }
    }

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

  // Toggle voice recording (Gemini MediaRecorder multimodal STT preferred with cross-platform MIME detection)
  const toggleListening = async () => {
    if (orbState === "listening" || isRecordingMedia) {
      stopListening();
      return;
    }

    if (isStartingRecordingRef.current) return;
    isStartingRecordingRef.current = true;

    stopSpeaking();
    setErrorMessage(null);
    setInteractionMode("voice");
    setRecordingSeconds(0);

    // Verify browser support for mediaDevices
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      isStartingRecordingRef.current = false;
      setOrbState("error");
      setErrorMessage("Microphone access is not supported by your browser or connection is not secure (HTTPS).");
      return;
    }

    try {
      setOrbState("listening");
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

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          audioChunksRef.current.push(e.data);
        }
      };

      recorder.onstop = async () => {
        stopAllMediaTracks(mediaStreamRef.current);
        mediaStreamRef.current = null;
        setIsRecordingMedia(false);

        if (recordingTimerRef.current) {
          clearInterval(recordingTimerRef.current);
          recordingTimerRef.current = null;
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
          setOrbState("idle");
          setErrorMessage("Audio recording is empty or too short. Please speak clearly into your microphone.");
          return;
        }

        setOrbState("thinking");
        try {
          const res = await apiClient.copilot.transcribeAudio(audioBlob, `speech.${ext}`);
          if (res.transcript && res.transcript.trim()) {
            const spokenWords = res.transcript.trim();
            setInputText(spokenWords);
            if (reviewBeforeSend) {
              setOrbState("idle");
              setTranscriptNotice("Transcript captured via Gemini! Review and edit your prompt below, then press Enter or Send.");
              setTimeout(() => {
                textInputRef.current?.focus();
              }, 50);
              return;
            } else {
              handleSend(spokenWords, true);
              return;
            }
          } else {
            setErrorMessage("No clear speech recognized. Please try speaking again.");
          }
        } catch (transcribeErr: any) {
          console.warn("Gemini transcription error:", transcribeErr);
          setErrorMessage(transcribeErr?.message || "Speech transcription failed. Please try again.");
        }
        setOrbState("idle");
      };

      recorder.onerror = () => {
        stopAllMediaTracks(mediaStreamRef.current);
        mediaStreamRef.current = null;
        setIsRecordingMedia(false);
        setOrbState("error");
        setErrorMessage("Microphone recording error occurred. Please try again.");
      };

      recorder.start(250);
      setIsRecordingMedia(true);

      let elapsed = 0;
      recordingTimerRef.current = setInterval(() => {
        elapsed += 1;
        setRecordingSeconds(elapsed);
        if (elapsed >= 60) {
          stopListening();
        }
      }, 1000);
    } catch (err: any) {
      stopAllMediaTracks(mediaStreamRef.current);
      mediaStreamRef.current = null;
      setIsRecordingMedia(false);
      setOrbState("error");
      if (err?.name === "NotAllowedError" || err?.name === "PermissionDeniedError") {
        setErrorMessage("Microphone permission denied. Please allow microphone access in your browser settings.");
      } else if (err?.name === "NotFoundError" || err?.name === "DevicesNotFoundError") {
        setErrorMessage("No microphone detected. Please connect an audio input device.");
      } else {
        setErrorMessage(err?.message || "Could not access microphone.");
      }
    } finally {
      isStartingRecordingRef.current = false;
    }
  };

  const handleSend = async (messageToSend?: string, wasSpoken?: boolean) => {
    const text = (messageToSend || inputText).trim();
    if (!text || loading) return;

    // Determine if this turn should trigger spoken output
    // If wasSpoken is explicitly provided, respect it; otherwise respect interactionMode
    const isVoiceTurn = wasSpoken !== undefined ? wasSpoken : interactionMode === "voice";

    stopSpeaking();
    setTranscriptNotice(null);
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
        input_mode: isVoiceTurn ? "voice" : "text",
        voice_preset: selectedVoice,
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

      // Phase 4 fix: Only play audio if this turn was initiated in voice mode AND user has not muted voice.
      // Text mode is completely silent (no audio playback, no background TTS).
      const shouldSpeak = isVoiceTurn && !isVoiceMuted;
      if (shouldSpeak) {
        if (response.speech_audio_base64) {
          playSynthesizedAudio(
            response.speech_audio_base64,
            response.speech_audio_format || "audio/mpeg"
          );
        } else {
          speakTextFallback(response.spoken_reply || response.reply);
        }
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
        approval_id: draft.approval_id || undefined,
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

  const handleSelectVoice = async (voiceId: string, gender: "masculine" | "feminine") => {
    setSelectedVoice(voiceId);
    setSelectedGender(gender);
    try {
      await apiClient.copilot.updatePreferences({
        voice_preset: voiceId,
        voice_gender: gender,
      });
    } catch (err) {
      console.warn("Failed to persist voice preference:", err);
    }
  };

  const handlePreviewVoice = async (voice: CopilotVoiceOption) => {
    if (previewingVoiceId === voice.id) {
      stopSpeaking();
      return;
    }

    stopSpeaking();
    setPreviewingVoiceId(voice.id);
    setOrbState("speaking");
    setIsSpeaking(true);

    try {
      const blob = await apiClient.copilot.getSpeechAudio(voice.sample_text, voice.id);
      const audioUrl = URL.createObjectURL(blob);
      const audio = new Audio(audioUrl);
      audioPlayerRef.current = audio;

      audio.onended = () => {
        setIsSpeaking(false);
        setOrbState("idle");
        setPreviewingVoiceId(null);
      };

      audio.onerror = () => {
        speakTextFallback(voice.sample_text, voice.id);
        setPreviewingVoiceId(null);
      };

      await audio.play();
    } catch (err) {
      console.warn("OpenAI TTS preview failed, using speech synthesis fallback:", err);
      speakTextFallback(voice.sample_text, voice.id);
      setPreviewingVoiceId(null);
    }
  };

  const handleReplaySpeech = async (text: string) => {
    stopSpeaking();
    setOrbState("speaking");
    setIsSpeaking(true);

    try {
      const blob = await apiClient.copilot.getSpeechAudio(text, selectedVoice);
      const audioUrl = URL.createObjectURL(blob);
      const audio = new Audio(audioUrl);
      audioPlayerRef.current = audio;

      audio.onplay = () => {
        setIsSpeaking(true);
        setOrbState("speaking");
      };

      audio.onended = () => {
        setIsSpeaking(false);
        setOrbState("idle");
        audioPlayerRef.current = null;
      };

      audio.onerror = () => {
        speakTextFallback(text);
      };

      await audio.play();
    } catch (err) {
      console.warn("OpenAI TTS replay failed, using speech synthesis fallback:", err);
      speakTextFallback(text);
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

  const formatSeconds = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const s = sec % 60;
    return `${mins}:${s < 10 ? "0" : ""}${s}`;
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
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-white tracking-tight">Mentor AI Copilot</h2>
                <span className="text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded bg-indigo-500/15 border border-indigo-500/30 text-indigo-300">
                  Live
                </span>
              </div>
              <p className="text-[10px] text-zinc-400 uppercase tracking-wider font-medium">
                {orbState === "listening"
                  ? "Listening to voice..."
                  : orbState === "thinking"
                  ? "Gemini Agent executing tools..."
                  : orbState === "speaking"
                  ? "Speaking AI response..."
                  : "Voice & Schedule Copilot"}
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
              onClick={() => setShowSettings(!showSettings)}
              className={`rounded-lg p-2 transition-colors ${
                showSettings ? "bg-indigo-600 text-white" : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
              }`}
              title="Voice Settings"
            >
              <Settings className="h-4 w-4" />
            </button>

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

        {/* Interaction Mode Switcher Bar (Phase 3: Text vs Voice Mode) */}
        <div className="flex items-center justify-between border-b border-zinc-800 bg-zinc-900/60 px-6 py-2.5">
          <div className="flex items-center gap-1 rounded-lg bg-zinc-950 p-1 border border-zinc-800">
            <button
              type="button"
              onClick={() => handleSwitchMode("text")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-all ${
                interactionMode === "text"
                  ? "bg-indigo-600 text-white shadow-sm font-semibold"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <MessageSquare className="h-3.5 w-3.5" />
              <span>Text Mode</span>
            </button>
            <button
              type="button"
              onClick={() => handleSwitchMode("voice")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-all ${
                interactionMode === "voice"
                  ? "bg-indigo-600 text-white shadow-sm font-semibold"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <Mic className="h-3.5 w-3.5" />
              <span>Voice Mode</span>
            </button>
          </div>
          <span className="text-[11px]">
            {interactionMode === "text" ? (
              <span className="text-zinc-400 flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-zinc-500" />
                Silent Markdown replies
              </span>
            ) : (
              <span className="text-indigo-300 font-medium flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                Speaks replies aloud
              </span>
            )}
          </span>
        </div>

        {/* Voice Preferences Drawer Panel */}
        {showSettings && (
          <div className="border-b border-zinc-800 bg-zinc-900/90 p-4 animate-in slide-in-from-top-2 duration-150">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs font-semibold text-white uppercase tracking-wider">
                Voice & Speech Preferences
              </h3>
              <span className="text-[10px] text-zinc-400">
                Voice & Acoustic Settings
              </span>
            </div>

            {/* Acoustic Profile & Safety Disclaimer */}
            <div className="rounded-xl bg-indigo-500/10 border border-indigo-500/20 p-2.5 mb-3 text-[11px] text-zinc-300">
              <div className="flex items-center gap-1.5 font-medium text-indigo-300 mb-0.5">
                <Sparkles className="h-3.5 w-3.5" />
                <span>Acoustic Profile & Synthesis</span>
              </div>
              <p className="text-zinc-400 leading-normal">
                Mentor AI uses speech recognition and high-fidelity speech synthesis. Select an acoustic profile below to customize voice responses.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {availableVoices
                .filter((v) => ["masculine", "feminine", "deep_vocal", "natural_vocal"].includes(v.id))
                .concat(
                  availableVoices.filter((v) => !["masculine", "feminine", "deep_vocal", "natural_vocal"].includes(v.id))
                )
                .slice(0, 4)
                .map((voice) => {
                  const isSelected =
                    selectedVoice === voice.id ||
                    (selectedVoice === "nova" && voice.id === "feminine") ||
                    (selectedVoice === "echo" && voice.id === "masculine") ||
                    (selectedVoice === "onyx" && voice.id === "deep_vocal") ||
                    (selectedVoice === "shimmer" && voice.id === "natural_vocal");
                  const isPreviewing = previewingVoiceId === voice.id;

                  return (
                    <div
                      key={voice.id}
                      className={`rounded-xl border p-3 transition-all flex flex-col justify-between ${
                        isSelected
                          ? "border-indigo-500 bg-indigo-500/10 shadow-sm ring-1 ring-indigo-500/30"
                          : "border-zinc-800 bg-zinc-950/70 hover:border-zinc-700"
                      }`}
                    >
                      <div>
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold text-white">{voice.name}</span>
                          <span className="text-[10px] uppercase font-bold text-zinc-400 bg-zinc-800/80 px-1.5 py-0.5 rounded border border-zinc-700/50">
                            {voice.perceived_sound}
                          </span>
                        </div>
                        <p className="mt-1 text-[11px] text-zinc-400 leading-relaxed">{voice.description}</p>
                      </div>

                      <div className="mt-3 flex items-center justify-between gap-2 pt-2 border-t border-zinc-800/60">
                        <button
                          type="button"
                          onClick={() => handlePreviewVoice(voice)}
                          className="flex items-center gap-1.5 text-[11px] font-medium text-zinc-300 hover:text-white transition-colors"
                        >
                          {isPreviewing ? (
                            <>
                              <Square className="h-3 w-3 fill-rose-400 text-rose-400" />
                              <span className="text-rose-300 font-semibold">Stop</span>
                            </>
                          ) : (
                            <>
                              <Play className="h-3 w-3 text-indigo-400" />
                              <span>Preview</span>
                            </>
                          )}
                        </button>

                        <button
                          type="button"
                          onClick={() => handleSelectVoice(voice.id, voice.perceived_sound)}
                          className={`rounded-lg px-2.5 py-1 text-[11px] font-semibold transition-all ${
                            isSelected
                              ? "bg-indigo-600 text-white shadow-sm"
                              : "bg-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-700"
                          }`}
                        >
                          {isSelected ? "Selected" : "Select"}
                        </button>
                      </div>
                    </div>
                  );
                })}
            </div>

            {/* Review Transcript Toggle */}
            <div className="mt-3 pt-3 border-t border-zinc-800 flex items-center justify-between">
              <div>
                <span className="text-xs font-medium text-white block">Review transcript before sending</span>
                <span className="text-[10px] text-zinc-400">Place spoken words into input box to edit before dispatch</span>
              </div>
              <button
                type="button"
                onClick={async () => {
                  const next = !reviewBeforeSend;
                  setReviewBeforeSend(next);
                  try {
                    await apiClient.copilot.updatePreferences({ review_before_send: next });
                  } catch (err) {
                    console.warn("Failed to update review_before_send preference", err);
                  }
                }}
                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                  reviewBeforeSend ? "bg-indigo-600" : "bg-zinc-800"
                }`}
                title={reviewBeforeSend ? "Transcript review enabled" : "Instant auto-send enabled"}
              >
                <span
                  className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                    reviewBeforeSend ? "translate-x-4.5" : "translate-x-1"
                  }`}
                />
              </button>
            </div>
          </div>
        )}

        {/* Central Siri/JARVIS Orb & Status Area */}
        <div className="flex flex-col items-center justify-center py-4 bg-gradient-to-b from-zinc-900/50 to-zinc-950 border-b border-zinc-800/60">
          <CopilotVoiceOrb
            state={orbState}
            size={130}
            onClick={toggleListening}
          />
          <p className="mt-2 text-xs font-medium text-zinc-400">
            {orbState === "listening"
              ? "Listening... (Click orb or mic when done speaking)"
              : orbState === "speaking"
              ? "Speaking response..."
              : orbState === "thinking"
              ? "Gemini Agent executing tools & retrieving live data..."
              : "Click orb to speak (English/Bangla) or type below"}
          </p>

          <span className="mt-1 text-[10px] text-zinc-500">
            AI-generated voice • {selectedVoice.toUpperCase()} ({selectedGender})
          </span>

          {/* Active AI-Generated Voice Indicator Bar */}
          {isSpeaking && (
            <div className="mt-2 flex items-center gap-2 rounded-full bg-indigo-600/20 border border-indigo-500/30 px-3 py-1 text-xs text-indigo-300 animate-pulse">
              <Volume2 className="h-3.5 w-3.5 text-indigo-400" />
              <span>AI-Generated Voice • {selectedVoice.toUpperCase()} ({selectedGender})</span>
              <button
                type="button"
                onClick={stopSpeaking}
                className="ml-2 rounded bg-zinc-800 px-2 py-0.5 text-[10px] font-medium text-zinc-300 hover:text-white hover:bg-zinc-700"
              >
                Stop
              </button>
            </div>
          )}

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
                {/* Tools Invoked Badges */}
                {msg.response?.tools_invoked && msg.response.tools_invoked.length > 0 && (
                  <div className="mb-2 flex flex-wrap gap-1">
                    {msg.response.tools_invoked.map((tool, idx) => (
                      <span
                        key={idx}
                        className="text-[9px] font-mono text-zinc-400 bg-zinc-950 px-1.5 py-0.5 rounded border border-zinc-800"
                      >
                        ⚡ {tool}
                      </span>
                    ))}
                  </div>
                )}

                {/* Natural Response Text with ChatGPT-style Markdown */}
                {msg.role === "assistant" ? (
                  <CopilotMarkdown content={msg.text} />
                ) : (
                  <div className="whitespace-pre-wrap">{msg.text}</div>
                )}

                {/* 0. Proactive Daily Briefing Card */}
                {msg.response?.daily_briefing && (
                  <div className="mt-3.5 rounded-xl border border-indigo-500/40 bg-zinc-950/90 p-4 shadow-xl">
                    {/* Header */}
                    <div className="flex items-center justify-between border-b border-zinc-800/80 pb-2.5 mb-3">
                      <div className="flex items-center gap-2">
                        <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-amber-500/10 text-amber-400">
                          <Sparkles className="h-3.5 w-3.5" />
                        </span>
                        <div>
                          <h4 className="text-xs font-semibold text-zinc-100">
                            Daily Briefing
                          </h4>
                          <span className="text-[10px] text-zinc-400 font-mono">
                            {msg.response.daily_briefing.target_date} • {msg.response.daily_briefing.timezone}
                          </span>
                        </div>
                      </div>
                      {msg.response.daily_briefing.streak_days > 0 && (
                        <div className="flex items-center gap-1 rounded-full bg-amber-500/10 px-2.5 py-0.5 border border-amber-500/20 text-[11px] font-semibold text-amber-400">
                          <Flame className="h-3 w-3 text-amber-500" />
                          <span>{msg.response.daily_briefing.streak_days}d streak</span>
                        </div>
                      )}
                    </div>

                    {/* Recommended First Focus Banner */}
                    {msg.response.daily_briefing.recommended_focus && (
                      <div className="rounded-lg border border-emerald-500/30 bg-emerald-950/20 p-3 mb-3">
                        <div className="flex items-center justify-between gap-2 mb-1.5">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-1">
                            <CheckCircle2 className="h-3 w-3" />
                            Recommended First Focus
                          </span>
                          {msg.response.daily_briefing.recommended_focus.priority && (
                            <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 text-[9px] font-mono font-bold text-emerald-300">
                              {msg.response.daily_briefing.recommended_focus.priority}
                            </span>
                          )}
                        </div>
                        <h5 className="text-xs font-bold text-white mb-1">
                          {msg.response.daily_briefing.recommended_focus.title}
                        </h5>
                        <p className="text-[11px] text-zinc-300 leading-relaxed mb-2">
                          {msg.response.daily_briefing.recommended_focus.reason}
                        </p>
                        {msg.response.daily_briefing.recommended_focus.scheduled_time && (
                          <div className="flex items-center gap-1 text-[10px] text-zinc-400 font-mono mb-2">
                            <Clock className="h-3 w-3 text-indigo-400" />
                            <span>Scheduled: {msg.response.daily_briefing.recommended_focus.scheduled_time}</span>
                          </div>
                        )}
                        {msg.response.daily_briefing.recommended_focus.deadline && (
                          <div className="flex items-center gap-1 text-[10px] text-amber-400 font-mono mb-2">
                            <AlertCircle className="h-3 w-3" />
                            <span>Due: {msg.response.daily_briefing.recommended_focus.deadline}</span>
                          </div>
                        )}
                        <button
                          type="button"
                          onClick={() => handleNavigate({ route: "/planner" })}
                          className="flex items-center gap-1 rounded bg-emerald-600 hover:bg-emerald-500 px-2.5 py-1 text-[11px] font-semibold text-white transition-colors"
                        >
                          <span>Focus in Daily Planner</span>
                          <ArrowRight className="h-3 w-3" />
                        </button>
                      </div>
                    )}

                    {/* Summary Metrics Grid */}
                    <div className="grid grid-cols-3 gap-2 mb-3 text-center">
                      <div className="rounded-lg bg-zinc-900/80 p-2 border border-zinc-800/80">
                        <span className="block text-sm font-bold text-indigo-300">
                          {msg.response.daily_briefing.scheduled_items_count}
                        </span>
                        <span className="text-[10px] text-zinc-500">Study Sessions</span>
                      </div>
                      <div className="rounded-lg bg-zinc-900/80 p-2 border border-zinc-800/80">
                        <span className={`block text-sm font-bold ${msg.response.daily_briefing.overdue_count > 0 ? "text-rose-400" : "text-emerald-400"}`}>
                          {msg.response.daily_briefing.overdue_count}
                        </span>
                        <span className="text-[10px] text-zinc-500">Overdue Tasks</span>
                      </div>
                      <div className="rounded-lg bg-zinc-900/80 p-2 border border-zinc-800/80">
                        <span className="block text-sm font-bold text-amber-300">
                          {msg.response.daily_briefing.upcoming_deadlines_count}
                        </span>
                        <span className="text-[10px] text-zinc-500">Deadlines (72h)</span>
                      </div>
                    </div>

                    {/* Quick Service Status / Actions */}
                    <div className="flex items-center justify-between pt-2 border-t border-zinc-800/60 text-[10px] text-zinc-400">
                      <div className="flex items-center gap-2">
                        <span className={`inline-flex items-center gap-1 ${msg.response.daily_briefing.calendar_status === "connected" ? "text-emerald-400" : "text-zinc-500"}`}>
                          <Calendar className="h-3 w-3" />
                          <span>{msg.response.daily_briefing.calendar_status === "connected" ? "Calendar synced" : "Calendar offline"}</span>
                        </span>
                        <span>•</span>
                        <span className={`inline-flex items-center gap-1 ${msg.response.daily_briefing.gmail_status === "connected" ? "text-emerald-400" : "text-zinc-500"}`}>
                          <Mail className="h-3 w-3" />
                          <span>{msg.response.daily_briefing.gmail_status === "connected" ? `${msg.response.daily_briefing.unread_emails_count} unread` : "Gmail offline"}</span>
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleNavigate({ route: "/tasks" })}
                          className="hover:text-indigo-300 underline transition-colors"
                        >
                          Tasks
                        </button>
                        <span>•</span>
                        <button
                          type="button"
                          onClick={() => handleNavigate({ route: "/calendar" })}
                          className="hover:text-indigo-300 underline transition-colors"
                        >
                          Calendar
                        </button>
                        <span>•</span>
                        <button
                          type="button"
                          onClick={() => handleNavigate({ route: "/planner" })}
                          className="hover:text-indigo-300 underline transition-colors"
                        >
                          Planner
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* 1. Schedule & Task Card */}
                {msg.response?.schedule_summary && !msg.response?.daily_briefing && (
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

                {/* 3. Email Draft Preview Card (Safety Gated with Approval ID) */}
                {msg.response?.email_draft && (
                  <div className="mt-3.5 rounded-xl border border-amber-500/30 bg-zinc-950/95 p-3.5 shadow-lg">
                    <div className="flex items-center gap-2 border-b border-zinc-800 pb-2 mb-2 text-xs font-semibold text-amber-400">
                      <Mail className="h-3.5 w-3.5" />
                      <span>Email Reply Draft (Confirmation Required Before Send)</span>
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
                {/* Assistant Message Actions: Copy Response & Listen */}
                {msg.role === "assistant" && (
                  <div className="mt-3 pt-2 border-t border-zinc-800/60 flex items-center justify-between text-[11px] text-zinc-400">
                    <span className="inline-flex items-center gap-1 text-[10px] text-zinc-500 uppercase font-semibold tracking-wider">
                      <Sparkles className="h-3 w-3 text-indigo-400" />
                      Mentor Copilot
                    </span>
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() => copyFullMessage(msg.id, msg.text)}
                        className="inline-flex items-center gap-1 text-zinc-400 hover:text-zinc-200 transition-colors"
                        title="Copy full response"
                      >
                        {copiedMessageId === msg.id ? (
                          <>
                            <Check className="h-3 w-3 text-emerald-400" />
                            <span className="text-emerald-400 font-medium">Copied</span>
                          </>
                        ) : (
                          <>
                            <Copy className="h-3 w-3" />
                            <span>Copy</span>
                          </>
                        )}
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          if (msg.response?.speech_audio_base64) {
                            playSynthesizedAudio(
                              msg.response.speech_audio_base64,
                              msg.response.speech_audio_format || "audio/mpeg"
                            );
                          } else {
                            handleReplaySpeech(msg.response?.spoken_reply || msg.text);
                          }
                        }}
                        className="inline-flex items-center gap-1 text-indigo-400 hover:text-indigo-300 font-medium transition-colors"
                        title="Listen to AI voice reading this response"
                      >
                        <Volume2 className="h-3.5 w-3.5" />
                        <span>Listen</span>
                      </button>
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
              onClick={() => handleSend(p, false)}
              disabled={loading}
              className="inline-flex items-center gap-1.5 rounded-full border border-zinc-800 bg-zinc-900/80 px-3 py-1 text-xs text-zinc-400 hover:border-indigo-500/40 hover:text-indigo-300 transition-colors"
            >
              <Sparkles className="h-3 w-3 text-indigo-400" />
              <span>{p}</span>
            </button>
          ))}
        </div>

        {/* Input Bar */}
        <div className="border-t border-zinc-800 bg-zinc-950 p-4 pb-6 sm:pb-4">
          {/* Active Voice Recording Indicator Banner */}
          {isRecordingMedia && (
            <div className="mb-3 flex items-center justify-between rounded-xl border border-rose-500/40 bg-rose-950/40 px-3.5 py-2 text-xs text-rose-300 shadow-lg backdrop-blur-md animate-in fade-in">
              <div className="flex items-center gap-2">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose-400 opacity-75" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-rose-500" />
                </span>
                <span className="font-semibold text-rose-200">Recording speech...</span>
                <span className="font-mono text-[11px] text-rose-300 font-bold">({formatSeconds(recordingSeconds)} / 1:00)</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={cancelListening}
                  className="rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 py-1 text-[11px] font-medium text-zinc-300 hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={stopListening}
                  className="inline-flex items-center gap-1 rounded-lg bg-rose-600 px-3 py-1 text-[11px] font-bold text-white hover:bg-rose-500 transition-colors shadow-sm"
                >
                  <Square className="h-2.5 w-2.5 fill-current" />
                  <span>Done</span>
                </button>
              </div>
            </div>
          )}

          {transcriptNotice && (
            <div className="mb-2.5 flex items-center justify-between gap-2 rounded-xl bg-indigo-500/10 border border-indigo-500/20 px-3 py-2 text-xs text-indigo-300 animate-in fade-in">
              <span className="truncate flex-1">{transcriptNotice}</span>
              <div className="flex items-center gap-1.5 shrink-0">
                <button
                  type="button"
                  onClick={() => {
                    handleSend(inputText, true);
                  }}
                  className="rounded-lg bg-indigo-600 px-2.5 py-1 text-[11px] font-bold text-white hover:bg-indigo-500 transition-colors shadow-sm"
                >
                  Send Now
                </button>
                <button
                  type="button"
                  onClick={() => setTranscriptNotice(null)}
                  className="text-zinc-400 hover:text-white p-0.5 rounded hover:bg-zinc-800"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend(undefined, interactionMode === "voice");
            }}
            className="flex items-center gap-2"
          >
            {/* Voice Input Button */}
            <button
              type="button"
              onClick={toggleListening}
              className={`rounded-xl p-2.5 transition-all ${
                orbState === "listening" || isRecordingMedia
                  ? "bg-rose-500/20 text-rose-400 ring-2 ring-rose-500 animate-pulse"
                  : interactionMode === "voice"
                  ? "bg-indigo-600/20 text-indigo-400 border border-indigo-500/30 hover:bg-indigo-600/30"
                  : "bg-zinc-900 text-zinc-400 hover:bg-zinc-800 hover:text-white border border-zinc-800"
              }`}
              title={
                orbState === "listening"
                  ? "Stop recording voice"
                  : interactionMode === "voice"
                  ? "Speak to Mentor (Voice Mode active)"
                  : "Speak to Mentor (Voice input)"
              }
            >
              {orbState === "listening" || isRecordingMedia ? (
                <MicOff className="h-5 w-5" />
              ) : (
                <Mic className="h-5 w-5" />
              )}
            </button>

            {/* Text Input Field */}
            <input
              ref={textInputRef}
              type="text"
              value={inputText}
              onChange={(e) => {
                setInputText(e.target.value);
                if (isSpeaking) stopSpeaking();
                if (transcriptNotice) setTranscriptNotice(null);
              }}
              placeholder={
                interactionMode === "text"
                  ? "Type your question (Silent text response)..."
                  : "Speak with mic or type here (Spoken voice response)..."
              }
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
