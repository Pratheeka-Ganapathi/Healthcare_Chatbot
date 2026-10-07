/**
 * The only module that touches the Pipecat SDK. Swapping to voice later changes this file.
 */
import { PipecatClient, RTVIEvent } from "@pipecat-ai/client-js";
import {
  PipecatClientProvider,
  usePipecatClient,
  useRTVIClientEvent,
} from "@pipecat-ai/client-react";
import { ProtobufFrameSerializer, WebSocketTransport } from "@pipecat-ai/websocket-transport";
import { createElement, useCallback, useMemo, type ReactNode } from "react";

import type { UIPayload } from "../ui/types";

export interface ChatEvents {
  onBotStarted: () => void;
  onBotText: (text: string) => void;
  onBotStopped: () => void;
  onUi: (payload: UIPayload) => void;
  onDisconnected: () => void;
}

export interface ChatControls {
  connect: (wsUrl: string) => Promise<void>;
  sendText: (text: string) => Promise<void>;
  disconnect: () => Promise<void>;
}

type TransportOptions = NonNullable<ConstructorParameters<typeof WebSocketTransport>[0]>;

/**
 * v1 is text only. The default media manager opens an AudioContext, which browsers keep
 * suspended until a user gesture, and the transport waits on it before sending
 * client-ready. This no-op manager keeps audio out of the picture; voice replaces it.
 */
function textOnlyMediaManager(): TransportOptions["mediaManager"] {
  const noop = async () => undefined;
  const manager = {
    setClientOptions: () => undefined,
    setUserAudioCallback: () => undefined,
    initialize: noop,
    connect: noop,
    disconnect: noop,
    bufferBotAudio: () => undefined,
    enableMic: () => undefined,
    isMicEnabled: false,
    selectedMic: {},
    selectedSpeaker: {},
    tracks: () => ({ local: {} }),
    getAllMics: async () => [],
    getAllCams: async () => [],
    getAllSpeakers: async () => [],
    updateMic: () => undefined,
    updateCam: () => undefined,
    updateSpeaker: () => undefined,
  };
  return manager as unknown as TransportOptions["mediaManager"];
}

function createClient(): PipecatClient {
  return new PipecatClient({
    transport: new WebSocketTransport({
      serializer: new ProtobufFrameSerializer(),
      mediaManager: textOnlyMediaManager(),
    }),
    enableMic: false,
    enableCam: false,
  });
}

export function ChatClientProvider({ children }: { children: ReactNode }) {
  const client = useMemo(() => createClient(), []);
  return createElement(PipecatClientProvider, { client }, children);
}

function isUiMessage(data: unknown): data is { type: "ui"; payload: UIPayload } {
  return (
    typeof data === "object" &&
    data !== null &&
    (data as { type?: unknown }).type === "ui" &&
    typeof (data as { payload?: unknown }).payload === "object"
  );
}

export function useChatEvents(events: ChatEvents): void {
  useRTVIClientEvent(
    RTVIEvent.BotLlmStarted,
    useCallback(() => events.onBotStarted(), [events]),
  );
  useRTVIClientEvent(
    RTVIEvent.BotLlmText,
    useCallback((data: { text: string }) => events.onBotText(data.text), [events]),
  );
  useRTVIClientEvent(
    RTVIEvent.BotLlmStopped,
    useCallback(() => events.onBotStopped(), [events]),
  );
  useRTVIClientEvent(
    RTVIEvent.ServerMessage,
    useCallback(
      (data: unknown) => {
        if (isUiMessage(data)) events.onUi(data.payload);
      },
      [events],
    ),
  );
  useRTVIClientEvent(
    RTVIEvent.Disconnected,
    useCallback(() => events.onDisconnected(), [events]),
  );
}

export function useChatControls(): ChatControls {
  const client = usePipecatClient();
  return useMemo<ChatControls>(
    () => ({
      connect: async (wsUrl) => {
        if (!client) throw new Error("Chat client is not ready");
        await client.connect({ wsUrl });
      },
      sendText: async (text) => {
        await client?.sendText(text, { run_immediately: true, audio_response: false });
      },
      disconnect: async () => {
        await client?.disconnect();
      },
    }),
    [client],
  );
}
