import type { AppointmentScope } from "../api/types";

const TABS: { value: AppointmentScope; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "upcoming", label: "Upcoming" },
  { value: "past", label: "Past" },
];

interface Props {
  value: AppointmentScope;
  onChange: (scope: AppointmentScope) => void;
}

export function ScopeTabs({ value, onChange }: Props) {
  return (
    <div className="tabs" role="tablist" aria-label="Which appointments">
      {TABS.map((tab) => (
        <button
          key={tab.value}
          type="button"
          role="tab"
          className="tab"
          aria-selected={tab.value === value}
          onClick={() => onChange(tab.value)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
