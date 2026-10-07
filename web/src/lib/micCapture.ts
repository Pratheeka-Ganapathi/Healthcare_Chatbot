/**
 * Microphone → 16 kHz mono 16-bit PCM chunks, for voice input.
 *
 * Asking for the mic triggers the browser's permission prompt the first time.
 * The AudioContext runs at 16 kHz where the browser allows it (it resamples properly);
 * otherwise (Firefox) the worklet decimates from the device rate.
 */

export const TARGET_RATE = 16_000;
const CHUNK_SAMPLES = 800; // 50 ms

export type MicError = "denied" | "no-mic" | "unsupported";

export interface Mic {
  stop: () => void;
}

const WORKLET = `
class Pcm16Writer extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.step = sampleRate / options.processorOptions.target;
    this.pos = 0;
    this.chunk = options.processorOptions.chunk;
    this.buf = new Int16Array(this.chunk);
    this.n = 0;
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    for (; this.pos < ch.length; this.pos += this.step) {
      const s = Math.max(-1, Math.min(1, ch[Math.floor(this.pos)]));
      this.buf[this.n++] = s < 0 ? s * 0x8000 : s * 0x7fff;
      if (this.n === this.chunk) {
        this.port.postMessage(this.buf.buffer, [this.buf.buffer]);
        this.buf = new Int16Array(this.chunk);
        this.n = 0;
      }
    }
    this.pos -= ch.length;
    return true;
  }
}
registerProcessor("pcm16-writer", Pcm16Writer);
`;

export function micSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    window.isSecureContext &&
    Boolean(navigator.mediaDevices?.getUserMedia) &&
    typeof AudioWorkletNode !== "undefined"
  );
}

function micError(error: unknown): MicError {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") return "denied";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "no-mic";
  return "unsupported";
}

function sourceFor(stream: MediaStream): { ctx: AudioContext; source: MediaStreamAudioSourceNode } {
  try {
    const ctx = new AudioContext({ sampleRate: TARGET_RATE });
    return { ctx, source: ctx.createMediaStreamSource(stream) };
  } catch {
    const ctx = new AudioContext();
    return { ctx, source: ctx.createMediaStreamSource(stream) };
  }
}

/** Throws a MicError string when the mic can't be opened. */
export async function openMic(onChunk: (pcm: ArrayBuffer) => void): Promise<Mic> {
  if (!micSupported()) throw "unsupported" satisfies MicError;
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
  } catch (error) {
    throw micError(error);
  }
  const { ctx, source } = sourceFor(stream);
  const url = URL.createObjectURL(new Blob([WORKLET], { type: "text/javascript" }));
  try {
    await ctx.audioWorklet.addModule(url);
  } finally {
    URL.revokeObjectURL(url);
  }
  const node = new AudioWorkletNode(ctx, "pcm16-writer", {
    processorOptions: { target: TARGET_RATE, chunk: CHUNK_SAMPLES },
  });
  node.port.onmessage = (event: MessageEvent<ArrayBuffer>) => onChunk(event.data);
  source.connect(node);
  await ctx.resume();
  let stopped = false;
  return {
    stop: () => {
      if (stopped) return;
      stopped = true;
      node.port.onmessage = null;
      source.disconnect();
      node.disconnect();
      stream.getTracks().forEach((track) => track.stop());
      void ctx.close();
    },
  };
}
