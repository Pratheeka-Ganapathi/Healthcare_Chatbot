import type { SlotButtons } from "../ui/types";

interface Props {
  payload: SlotButtons;
  active: boolean;
  onSend: (text: string) => void;
}

export function SlotChips({ payload, active, onSend }: Props) {
  const showDoctor = new Set(payload.groups.map((g) => g.doctor)).size > 1;
  return (
    <div className="slots">
      {payload.groups.map((group) => (
        <section key={`${group.date_label}-${group.doctor}`} className="slot-group">
          <h3 className="slot-date">
            {group.date_label}
            {showDoctor && <span className="slot-doctor">{group.doctor}</span>}
          </h3>
          <div className="chips">
            {group.slots.map((slot) => (
              <button
                key={slot.text}
                type="button"
                className="chip chip-time"
                disabled={!active}
                onClick={() => onSend(slot.text)}
              >
                {slot.label}
              </button>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
