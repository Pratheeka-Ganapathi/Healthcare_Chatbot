import type { QuickReplies as QuickRepliesPayload } from "../ui/types";

interface Props {
  payload: QuickRepliesPayload;
  active: boolean;
  onSend: (text: string) => void;
}

export function QuickReplies({ payload, active, onSend }: Props) {
  return (
    <div className="chips" role="group" aria-label="Suggested replies">
      {payload.options.map((option) => (
        <button
          key={option}
          type="button"
          className="chip"
          disabled={!active}
          onClick={() => onSend(option)}
        >
          {option}
        </button>
      ))}
    </div>
  );
}
