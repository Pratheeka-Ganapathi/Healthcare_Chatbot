import { useCallback, useEffect, useRef, useState } from "react";

import { STT_URL } from "../config";
import { startSpeech, type SpeechError, type SpeechSession } from "../transport/speechClient";
import { draftText, startDraft, withTranscript, type VoiceDraft } from "./voiceDraft";

export type VoiceStatus = "idle" | "starting" | "listening" | "finishing";

export interface VoiceInput {
  status: VoiceStatus;
  error: SpeechError | null;
  /** Mic button: start listening (keeping what is already typed) or stop. */
  toggle: (currentDraft: string) => void;
  /** The message was sent: stop at once and drop late words. */
  abort: () => void;
}

/** Speech fills the message box through ``setDraft``; it is never sent from here. */
export function useVoiceInput(setDraft: (text: string) => void): VoiceInput {
  const [status, setStatus] = useState<VoiceStatus>("idle");
  const [error, setError] = useState<SpeechError | null>(null);
  const session = useRef<SpeechSession | null>(null);
  const draft = useRef<VoiceDraft>(startDraft(""));

  const begin = useCallback(
    async (currentDraft: string) => {
      setError(null);
      setStatus("starting");
      draft.current = startDraft(currentDraft);
      try {
        session.current = await startSpeech(STT_URL, {
          onTranscript: (text, final) => {
            draft.current = withTranscript(draft.current, text, final);
            setDraft(draftText(draft.current));
          },
          onEnd: (endError) => {
            session.current = null;
            setStatus("idle");
            if (endError) setError(endError);
          },
        });
        setStatus((s) => (s === "starting" ? "listening" : s));
      } catch (startError) {
        setStatus("idle");
        setError(typeof startError === "string" ? (startError as SpeechError) : "unavailable");
      }
    },
    [setDraft],
  );

  const toggle = useCallback(
    (currentDraft: string) => {
      if (session.current) {
        setStatus("finishing");
        session.current.stop();
      } else if (status === "idle") {
        void begin(currentDraft);
      }
    },
    [begin, status],
  );

  const abort = useCallback(() => session.current?.abort(), []);
  useEffect(() => () => session.current?.abort(), []);

  return { status, error, toggle, abort };
}
