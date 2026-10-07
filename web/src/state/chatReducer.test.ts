import { describe, expect, it } from "vitest";

import type { UIPayload } from "../ui/types";
import {
  chatReducer,
  initialState,
  inputEnabled,
  type ChatAction,
  type ChatState,
} from "./chatReducer";

const run = (actions: ChatAction[], start: ChatState = { ...initialState, status: "ready" }) =>
  actions.reduce(chatReducer, start);

const slots: UIPayload = {
  type: "slot_buttons",
  groups: [
    {
      date_label: "Wed 7 Oct",
      doctor: "Dr. Rao",
      slots: [{ label: "6:15 PM", text: "Wed 7 Oct, 6:15 PM" }],
    },
  ],
};
const replies: UIPayload = { type: "quick_replies", options: ["Confirm"] };

describe("chatReducer", () => {
  it("renders UI only after the sentence that introduces it", () => {
    const state = run([
      { type: "ui", payload: slots },
      { type: "botStarted" },
      { type: "botText", text: "Here are " },
      { type: "botText", text: "the times." },
      { type: "botStopped" },
    ]);
    expect(state.items.map((i) => i.kind)).toEqual(["bot", "ui"]);
    expect(state.items[0]).toMatchObject({ text: "Here are the times." });
  });

  it("keeps UI queued across an empty response", () => {
    const state = run([
      { type: "ui", payload: slots },
      { type: "botStarted" },
      { type: "botStopped" },
    ]);
    expect(state.items).toHaveLength(0);
    expect(state.pendingUi).toHaveLength(1);
    expect(chatReducer(state, { type: "flushUi" }).items).toHaveLength(1);
  });

  it("disables earlier interactive blocks when a newer bot message arrives", () => {
    const state = run([
      { type: "botStarted" },
      { type: "botText", text: "Pick one." },
      { type: "ui", payload: slots },
      { type: "botStopped" },
      { type: "userSent", text: "Wed 7 Oct, 6:15 PM" },
      { type: "botStarted" },
      { type: "botText", text: "Please confirm." },
      { type: "ui", payload: replies },
      { type: "botStopped" },
    ]);
    const ui = state.items.filter((i) => i.kind === "ui");
    expect(ui.map((i) => (i.kind === "ui" ? i.active : null))).toEqual([false, true]);
  });

  it("keeps input open until a handoff card ends the chat", () => {
    const open = run([{ type: "connected" }]);
    expect(inputEnabled(open)).toBe(true);
    const handoff: UIPayload = {
      type: "handoff_card",
      desk_number: "080 0000 1234",
      ticket_id: "CB-0001",
    };
    const ended = chatReducer(chatReducer(open, { type: "ui", payload: handoff }), {
      type: "flushUi",
    });
    expect(ended.status).toBe("ended");
    expect(inputEnabled(ended)).toBe(false);
  });

  it("strips markdown from bot text", () => {
    const state = run([
      { type: "botStarted" },
      { type: "botText", text: "**Dr. Rao** is available" },
      { type: "botStopped" },
    ]);
    expect(state.items[0]).toMatchObject({ text: "Dr. Rao is available" });
  });
});
