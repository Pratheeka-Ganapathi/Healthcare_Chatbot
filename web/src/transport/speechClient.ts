/**
 * Voice input: mic audio to the server's /stt socket (Pipecat frames), transcript back.
 * The transcript only fills the message box; the patient sends it with Enter.
 */
import type { RTVIMessage } from "@pipecat-ai/client-js";
import { ProtobufFrameSerializer } from "@pipecat-ai/websocket-transport";

import { openMic, TARGET_RATE, type Mic, type MicError } from "../lib/micCapture";

export type SpeechError = MicError | "unavailable";

export interface SpeechHandlers {
  onTranscript: (text: string, final: boolean) => void;
  /** Called once, when listening is over. ``error`` is set if it ended badly. */
  onEnd: (error?: SpeechError) => void;
}

export interface SpeechSession {
  /** Stop the mic; the last words are transcribed before the session ends. */
  stop: () => void;
  /** End now and drop anything still on its way (the message was just sent). */
  abort: () => void;
}

export const MAX_LISTEN_MS = 60_000;
const FINAL_WAIT_MS = 2_500;

interface ServerMessage {
  type?: string;
  text?: string;
  final?: boolean;
}

/** Opens the mic (permission prompt) and the socket. Throws a SpeechError string. */
export async function startSpeech(url: string, handlers: SpeechHandlers): Promise<SpeechSession> {
  const serializer = new ProtobufFrameSerializer();
  const queued: Uint8Array[] = [];
  let ws: WebSocket | null = null;
  const send = (data: Uint8Array) => {
    if (ws?.readyState === WebSocket.OPEN) ws.send(data);
    else queued.push(data);
  };
  const mic: Mic = await openMic((pcm) => send(serializer.serializeAudio(pcm, TARGET_RATE, 1)));

  let stopping = false;
  let ended = false;
  let pending = false; // words heard but not yet final
  let timer: ReturnType<typeof setTimeout> | undefined;
  const finish = (error?: SpeechError) => {
    if (ended) return;
    ended = true;
    clearTimeout(timer);
    mic.stop();
    ws?.close();
    handlers.onEnd(error);
  };
  const stop = () => {
    if (stopping || ended) return;
    stopping = true;
    mic.stop();
    if (!pending) return finish();
    send(serializer.serializeMessage({ type: "speech-end" } as unknown as RTVIMessage));
    clearTimeout(timer);
    timer = setTimeout(() => finish(), FINAL_WAIT_MS);
  };

  ws = new WebSocket(url);
  ws.onopen = () => queued.splice(0).forEach((data) => ws?.send(data));
  ws.onmessage = async (event: MessageEvent) => {
    const decoded = await serializer.deserialize(event.data).catch(() => null);
    if (ended || decoded?.type !== "message") return;
    const message = decoded.message as unknown as ServerMessage;
    if (message.type === "speech-error") return finish("unavailable");
    if (message.type !== "transcript" || !message.text) return;
    pending = !message.final;
    handlers.onTranscript(message.text, Boolean(message.final));
    if (stopping && message.final) finish();
  };
  ws.onerror = () => finish("unavailable");
  ws.onclose = () => finish(stopping ? undefined : "unavailable");
  timer = setTimeout(stop, MAX_LISTEN_MS);
  return { stop, abort: () => finish() };
}
