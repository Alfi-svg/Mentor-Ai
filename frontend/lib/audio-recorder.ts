/**
 * Cross-platform Audio Recording Utilities for Android, iOS Safari, and Desktop.
 * Accurately detects supported MediaRecorder MIME types and manages MediaStream tracks.
 */

export interface SupportedAudioMime {
  mimeType: string;
  extension: string;
}

export function detectSupportedAudioMime(): SupportedAudioMime {
  if (typeof window === "undefined" || typeof MediaRecorder === "undefined") {
    return { mimeType: "audio/webm", extension: "webm" };
  }

  const candidates: SupportedAudioMime[] = [
    { mimeType: "audio/webm;codecs=opus", extension: "webm" },
    { mimeType: "audio/webm", extension: "webm" },
    { mimeType: "audio/mp4", extension: "mp4" },
    { mimeType: "audio/aac", extension: "aac" },
    { mimeType: "audio/ogg;codecs=opus", extension: "ogg" },
    { mimeType: "audio/wav", extension: "wav" },
  ];

  for (const candidate of candidates) {
    try {
      if (typeof MediaRecorder.isTypeSupported === "function" && MediaRecorder.isTypeSupported(candidate.mimeType)) {
        return candidate;
      }
    } catch {
      // ignore check error
    }
  }

  // Fallback to empty mimeType so MediaRecorder selects browser default container
  return { mimeType: "", extension: "webm" };
}

export function stopAllMediaTracks(stream: MediaStream | null | undefined): void {
  if (!stream) return;
  try {
    stream.getTracks().forEach((track) => {
      try {
        track.stop();
      } catch {
        // ignore track stop error
      }
    });
  } catch {
    // ignore
  }
}
