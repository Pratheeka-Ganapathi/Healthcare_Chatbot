import type { VoiceStatus } from "../voice/useVoiceInput";

interface Props {
  status: VoiceStatus;
  disabled: boolean;
  onClick: () => void;
}

const LABELS: Record<VoiceStatus, string> = {
  idle: "Speak your message",
  starting: "Starting the microphone",
  listening: "Stop listening",
  finishing: "Finishing",
};

export function MicButton({ status, disabled, onClick }: Props) {
  const active = status !== "idle";
  return (
    <button
      type="button"
      className={`mic-button${active ? " mic-active" : ""}`}
      onClick={onClick}
      disabled={disabled || status === "starting" || status === "finishing"}
      aria-pressed={active}
      aria-label={LABELS[status]}
      title={LABELS[status]}
    >
      <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
        <rect x="9" y="3" width="6" height="11" rx="3" fill="currentColor" />
        <path
          d="M6 11a6 6 0 0 0 12 0M12 17v4M9 21h6"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    </button>
  );
}
