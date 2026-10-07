/**
 * Reads bot replies aloud with the browser's built-in speech (no server TTS).
 * Volume and mute are remembered per browser; storage may be unavailable, so every
 * read and write is guarded.
 */

export interface SpeakerSettings {
  muted: boolean;
  /** 0 to 1. */
  volume: number;
}

const STORAGE_KEY = "citycare.speaker";
export const DEFAULT_SPEAKER: SpeakerSettings = { muted: false, volume: 0.8 };

export function ttsSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export function loadSpeaker(): SpeakerSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_SPEAKER;
    const parsed = JSON.parse(raw) as Partial<SpeakerSettings>;
    const volume = Number(parsed.volume);
    return {
      muted: parsed.muted === true,
      volume: Number.isFinite(volume) ? Math.min(1, Math.max(0, volume)) : DEFAULT_SPEAKER.volume,
    };
  } catch {
    return DEFAULT_SPEAKER;
  }
}

export function saveSpeaker(settings: SpeakerSettings): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // storage blocked: settings last for this page only
  }
}

/** Browsers refuse speech until the user has interacted with the page. */
export function mayAutoplay(): boolean {
  return navigator.userActivation?.hasBeenActive ?? true;
}

/** Indian English if the device has it, then any English voice. */
function pickVoice(): SpeechSynthesisVoice | undefined {
  const voices = window.speechSynthesis.getVoices();
  return (
    voices.find((v) => v.lang === "en-IN") ??
    voices.find((v) => v.lang.startsWith("en-GB")) ??
    voices.find((v) => v.lang.startsWith("en"))
  );
}

export function speak(text: string, volume: number): void {
  if (!ttsSupported() || !text.trim()) return;
  const synth = window.speechSynthesis;
  synth.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  const voice = pickVoice();
  if (voice) utterance.voice = voice;
  utterance.lang = voice?.lang ?? "en-IN";
  utterance.volume = volume;
  synth.speak(utterance);
}

export function stopSpeaking(): void {
  if (ttsSupported()) window.speechSynthesis.cancel();
}
