import { describe, expect, it } from "vitest";

import { renderUi } from "./registry";
import type { UIPayload } from "./types";

describe("renderUi", () => {
  it("renders every payload type", () => {
    const payloads: UIPayload[] = [
      { type: "quick_replies", options: ["Confirm"] },
      { type: "menu", options: [{ label: "Book an appointment", text: "I want to book" }] },
      { type: "doctor_cards", doctors: [] },
      { type: "slot_buttons", groups: [] },
      { type: "appointment_buttons", appointments: [] },
      {
        type: "confirmation_card",
        doctor: "Dr. Rao",
        specialty: "General Medicine",
        date: "Wed 7 Oct",
        time: "6:15 PM",
        visit_type: "new",
        appointment_ref: "A-00001",
      },
      { type: "handoff_card", desk_number: "080 0000 1234", ticket_id: "CB-0001" },
    ];
    for (const payload of payloads) {
      expect(renderUi(payload, { active: true, onSend: () => undefined })).toBeTruthy();
    }
  });
});
