import { generatePassword, MIN_PASSWORD_LENGTH } from "../lib/password";

interface Props {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
}

/** A password the admin hands over, so it is shown in clear, with a generator. */
export function GeneratedPasswordField({ id, label, value, onChange }: Props) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="input-with-button">
        <input
          id={id}
          type="text"
          className="mono"
          autoComplete="off"
          spellCheck={false}
          minLength={MIN_PASSWORD_LENGTH}
          required
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-describedby={`${id}-hint`}
        />
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => onChange(generatePassword())}
        >
          Generate
        </button>
      </div>
      <p className="hint" id={`${id}-hint`}>
        At least {MIN_PASSWORD_LENGTH} characters. Share it with the doctor privately; they can
        change it after signing in.
      </p>
    </div>
  );
}
