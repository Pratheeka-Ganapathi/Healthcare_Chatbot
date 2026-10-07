import { stripMarkdown } from "../lib/text";
import type { UIPayload } from "../ui/types";

export type Status = "waking" | "connecting" | "ready" | "ended" | "error";

export type ChatItem =
  | { id: number; kind: "bot" | "user"; text: string }
  | { id: number; kind: "ui"; payload: UIPayload; active: boolean };

export interface ChatState {
  status: Status;
  items: ChatItem[];
  /** Text of the bot response being streamed; null when no response is open. */
  streaming: string | null;
  /** UI blocks waiting for the sentence that introduces them. */
  pendingUi: UIPayload[];
  nextId: number;
}

export type ChatAction =
  | { type: "waking" }
  | { type: "connecting" }
  | { type: "connected" }
  | { type: "failed" }
  | { type: "userSent"; text: string }
  | { type: "botStarted" }
  | { type: "botText"; text: string }
  | { type: "botStopped" }
  | { type: "ui"; payload: UIPayload }
  | { type: "flushUi" }
  | { type: "disconnected" }
  | { type: "reset" };

export const initialState: ChatState = {
  status: "waking",
  items: [],
  streaming: null,
  pendingUi: [],
  nextId: 1,
};

const INTERACTIVE = new Set<UIPayload["type"]>([
  "quick_replies",
  "menu",
  "doctor_cards",
  "slot_buttons",
  "appointment_buttons",
]);

export function isInteractive(payload: UIPayload): boolean {
  return INTERACTIVE.has(payload.type);
}

function deactivateAll(items: ChatItem[]): ChatItem[] {
  return items.map((item) =>
    item.kind === "ui" && item.active ? { ...item, active: false } : item,
  );
}

/** UI blocks are appended in order; a handoff card ends the chat. */
function placeUi(state: ChatState, payloads: UIPayload[]): ChatState {
  let next = state;
  for (const payload of payloads) {
    const item: ChatItem = { id: next.nextId, kind: "ui", payload, active: isInteractive(payload) };
    const status: Status = payload.type === "handoff_card" ? "ended" : next.status;
    next = { ...next, items: [...next.items, item], nextId: next.nextId + 1, status };
  }
  return next;
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "waking":
      return { ...state, status: "waking" };
    case "connecting":
      return { ...state, status: "connecting" };
    case "connected":
      return { ...state, status: "ready" };
    case "failed":
      return { ...state, status: "error" };
    case "userSent": {
      const item: ChatItem = { id: state.nextId, kind: "user", text: action.text };
      return { ...state, items: [...state.items, item], nextId: state.nextId + 1 };
    }
    case "botStarted":
      return { ...state, streaming: "" };
    case "botText":
      return { ...state, streaming: (state.streaming ?? "") + action.text };
    case "botStopped": {
      const text = stripMarkdown(state.streaming ?? "");
      if (!text) return { ...state, streaming: null };
      const message: ChatItem = { id: state.nextId, kind: "bot", text };
      const withMessage: ChatState = {
        ...state,
        items: [...deactivateAll(state.items), message],
        nextId: state.nextId + 1,
        streaming: null,
        pendingUi: [],
      };
      return placeUi(withMessage, state.pendingUi);
    }
    case "ui":
      return { ...state, pendingUi: [...state.pendingUi, action.payload] };
    case "flushUi":
      if (state.streaming !== null || state.pendingUi.length === 0) return state;
      return placeUi({ ...state, pendingUi: [] }, state.pendingUi);
    case "disconnected":
      return state.status === "ended" ? state : { ...state, status: "ended" };
    case "reset":
      return { ...initialState, status: "connecting" };
  }
}

export function inputEnabled(state: ChatState): boolean {
  return state.status === "ready";
}
