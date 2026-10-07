import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import { Bubble, TypingIndicator } from "./components/Bubble";
import { DemoNotice, TryItPanel } from "./components/DemoNotice";
import { MicButton } from "./components/MicButton";
import { VolumeControl } from "./components/VolumeControl";
import { API_URL, WS_URL } from "./config";
import { chatReducer, initialState, inputEnabled } from "./state/chatReducer";
import { useChatControls, useChatEvents, type ChatEvents } from "./transport/chatClient";
import { renderUi } from "./ui/registry";
import type { SpeechError } from "./transport/speechClient";
import { useSpeaker } from "./voice/useSpeaker";
import { useVoiceInput } from "./voice/useVoiceInput";

const WAKE_TIMEOUT_MS = 90_000;
const UI_FALLBACK_MS = 1200;

const VOICE_ERRORS: Record<SpeechError, string> = {
  denied:
    "Microphone access is blocked. Allow it in your browser's site settings to speak your message.",
  "no-mic": "No microphone was found. Please type your message.",
  unsupported: "Voice input isn't supported in this browser. Please type your message.",
  unavailable: "Voice input isn't available right now. Please type your message.",
};

async function waitForServer(signal: AbortSignal): Promise<void> {
  const deadline = Date.now() + WAKE_TIMEOUT_MS;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${API_URL}/healthz`, { signal });
      if (response.ok) return;
    } catch (error) {
      if (signal.aborted) throw error;
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  throw new Error("Server did not wake up");
}

export function App() {
  const [state, dispatch] = useReducer(chatReducer, initialState);
  const [draft, setDraft] = useState("");
  const controls = useChatControls();
  const started = useRef(false);
  const listEnd = useRef<HTMLDivElement>(null);
  const speaker = useSpeaker();
  const voice = useVoiceInput(setDraft);
  const spokenUpTo = useRef(0);

  const events = useMemo<ChatEvents>(
    () => ({
      onBotStarted: () => dispatch({ type: "botStarted" }),
      onBotText: (text) => dispatch({ type: "botText", text }),
      onBotStopped: () => dispatch({ type: "botStopped" }),
      onUi: (payload) => dispatch({ type: "ui", payload }),
      onDisconnected: () => dispatch({ type: "disconnected" }),
    }),
    [],
  );
  useChatEvents(events);

  const start = useCallback(async () => {
    const controller = new AbortController();
    try {
      dispatch({ type: "waking" });
      await waitForServer(controller.signal);
      dispatch({ type: "connecting" });
      await controls.connect(WS_URL);
      dispatch({ type: "connected" });
    } catch {
      dispatch({ type: "failed" });
    }
  }, [controls]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void start();
  }, [start]);

  useEffect(() => {
    if (state.pendingUi.length === 0 || state.streaming !== null) return;
    const timer = setTimeout(() => dispatch({ type: "flushUi" }), UI_FALLBACK_MS);
    return () => clearTimeout(timer);
  }, [state.pendingUi, state.streaming]);

  // Read each new bot reply aloud once (not while the patient is speaking).
  const { say } = speaker;
  const listening = voice.status !== "idle";
  useEffect(() => {
    const latest = [...state.items].reverse().find((item) => item.kind === "bot");
    if (latest?.kind !== "bot" || latest.id <= spokenUpTo.current) return;
    spokenUpTo.current = latest.id;
    if (!listening) say(latest.text);
  }, [state.items, say, listening]);

  useEffect(() => {
    listEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [state.items.length, state.streaming]);

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      voice.abort();
      speaker.hush();
      dispatch({ type: "userSent", text: trimmed });
      void controls.sendText(trimmed);
    },
    [controls, voice, speaker],
  );

  const restart = useCallback(async () => {
    await controls.disconnect();
    dispatch({ type: "reset" });
    spokenUpTo.current = 0;
    await start();
  }, [controls, start]);

  const canType = inputEnabled(state);

  return (
    <div className="shell">
      <header className="masthead">
        <div className="masthead-top">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true" />
            <div>
              <h1>City Care Clinic</h1>
              <p className="brand-sub">Front desk, Indiranagar, Bangalore</p>
            </div>
          </div>
          <VolumeControl speaker={speaker} />
        </div>
        <DemoNotice />
        <TryItPanel onUse={setDraft} />
      </header>

      <main className="conversation" aria-live="polite">
        {state.status === "waking" && <p className="status">Waking up the demo server...</p>}
        {state.status === "connecting" && <p className="status">Connecting...</p>}
        {state.status === "error" && (
          <p className="status status-error">
            Could not reach the clinic assistant. Check that the server is running, then{" "}
            <button type="button" className="link-button" onClick={() => void start()}>
              try again
            </button>
            .
          </p>
        )}
        {state.items.map((item) =>
          item.kind === "ui" ? (
            <div key={item.id} className="ui-block">
              {renderUi(item.payload, { active: item.active && canType, onSend: send })}
            </div>
          ) : (
            <Bubble key={item.id} from={item.kind} text={item.text} />
          ),
        )}
        {state.streaming === "" && <TypingIndicator />}
        {state.streaming && <Bubble from="bot" text={state.streaming} />}
        <div ref={listEnd} />
      </main>

      <footer className="composer-wrap">
        {state.status === "ended" ? (
          <button type="button" className="restart" onClick={() => void restart()}>
            Start new chat
          </button>
        ) : (
          <form
            className="composer"
            onSubmit={(event) => {
              event.preventDefault();
              send(draft);
              setDraft("");
            }}
          >
            <label htmlFor="message" className="sr-only">
              Message
            </label>
            <input
              id="message"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={
                listening ? "Listening... speak now" : canType ? "Type a message" : "Please wait"
              }
              disabled={!canType}
              readOnly={listening}
              maxLength={500}
              autoComplete="off"
            />
            <MicButton
              status={voice.status}
              disabled={!canType}
              onClick={() => {
                speaker.hush();
                voice.toggle(draft);
              }}
            />
            <button type="submit" disabled={!canType || !draft.trim()}>
              Send
            </button>
          </form>
        )}
        {voice.error && state.status !== "ended" && (
          <p className="voice-note" role="status">
            {VOICE_ERRORS[voice.error]}
          </p>
        )}
      </footer>
    </div>
  );
}
