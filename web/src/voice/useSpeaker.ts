import { useCallback, useEffect, useState } from "react";

import {
  loadSpeaker,
  mayAutoplay,
  saveSpeaker,
  speak,
  stopSpeaking,
  ttsSupported,
  type SpeakerSettings,
} from "../lib/speaker";

export interface Speaker extends SpeakerSettings {
  supported: boolean;
  toggleMute: () => void;
  setVolume: (volume: number) => void;
  /** Read a bot reply aloud unless muted or the page hasn't been touched yet. */
  say: (text: string) => void;
  hush: () => void;
}

export function useSpeaker(): Speaker {
  const [settings, setSettings] = useState<SpeakerSettings>(loadSpeaker);
  const supported = ttsSupported();

  useEffect(() => saveSpeaker(settings), [settings]);
  useEffect(() => stopSpeaking, []);

  const toggleMute = useCallback(() => {
    setSettings((s) => {
      if (!s.muted) stopSpeaking();
      return { muted: !s.muted, volume: s.volume === 0 ? 0.8 : s.volume };
    });
  }, []);

  const setVolume = useCallback((volume: number) => {
    if (volume === 0) stopSpeaking();
    setSettings({ volume, muted: volume === 0 });
  }, []);

  const { muted, volume } = settings;
  const say = useCallback(
    (text: string) => {
      if (supported && !muted && volume > 0 && mayAutoplay()) speak(text, volume);
    },
    [supported, muted, volume],
  );

  return { ...settings, supported, toggleMute, setVolume, say, hush: stopSpeaking };
}
