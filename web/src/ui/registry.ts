/**
 * ui.type → component. The switch is exhaustive over the generated union, so a new
 * payload type on the server fails the type check here until it is handled.
 */
import { createElement, type ReactElement } from "react";

import { AppointmentButtons } from "../components/AppointmentButtons";
import { ConfirmationCard } from "../components/ConfirmationCard";
import { DoctorCardList } from "../components/DoctorCard";
import { HandoffCard } from "../components/HandoffCard";
import { MenuOptions } from "../components/MenuOptions";
import { QuickReplies } from "../components/QuickReplies";
import { SlotChips } from "../components/SlotChips";
import type { UIPayload } from "./types";

export interface RenderOptions {
  active: boolean;
  onSend: (text: string) => void;
}

export function renderUi(payload: UIPayload, { active, onSend }: RenderOptions): ReactElement {
  switch (payload.type) {
    case "quick_replies":
      return createElement(QuickReplies, { payload, active, onSend });
    case "menu":
      return createElement(MenuOptions, { payload, active, onSend });
    case "doctor_cards":
      return createElement(DoctorCardList, { payload, active, onSend });
    case "slot_buttons":
      return createElement(SlotChips, { payload, active, onSend });
    case "appointment_buttons":
      return createElement(AppointmentButtons, { payload, active, onSend });
    case "confirmation_card":
      return createElement(ConfirmationCard, { payload });
    case "handoff_card":
      return createElement(HandoffCard, { payload });
    default:
      return assertNever(payload);
  }
}

function assertNever(value: never): never {
  throw new Error(`Unhandled UI payload: ${JSON.stringify(value)}`);
}
