import type { Menu } from "../ui/types";

interface Props {
  payload: Menu;
  active: boolean;
  onSend: (text: string) => void;
}

/** Stacked full-width options under the greeting. A tap sends the option's text. */
export function MenuOptions({ payload, active, onSend }: Props) {
  return (
    <div className="menu" role="group" aria-label="What would you like to do?">
      {payload.options.map((option) => (
        <button
          key={option.text}
          type="button"
          className="menu-option"
          disabled={!active}
          onClick={() => onSend(option.text)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
