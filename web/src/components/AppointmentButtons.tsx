import type { AppointmentButtons as AppointmentButtonsPayload } from "../ui/types";

interface Props {
  payload: AppointmentButtonsPayload;
  active: boolean;
  onSend: (text: string) => void;
}

export function AppointmentButtons({ payload, active, onSend }: Props) {
  return (
    <div className="appointments" role="group" aria-label="Your upcoming appointments">
      {payload.appointments.map((appt) => (
        <button
          key={appt.text}
          type="button"
          className="appointment"
          disabled={!active}
          onClick={() => onSend(appt.text)}
        >
          {appt.label}
        </button>
      ))}
    </div>
  );
}
