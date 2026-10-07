interface Props {
  from: "bot" | "user";
  text: string;
}

const URL_PATTERN = /(https?:\/\/[^\s)]+)/g;

function linkify(text: string) {
  return text.split(URL_PATTERN).map((part, i) =>
    i % 2 === 1 ? (
      <a key={i} href={part} target="_blank" rel="noreferrer">
        {part}
      </a>
    ) : (
      part
    ),
  );
}

export function Bubble({ from, text }: Props) {
  return (
    <div className={`bubble bubble-${from}`}>
      <span className="sr-only">{from === "bot" ? "Clinic assistant: " : "You: "}</span>
      {linkify(text)}
    </div>
  );
}

export function TypingIndicator() {
  return (
    <div className="bubble bubble-bot typing" aria-label="The assistant is typing">
      <span />
      <span />
      <span />
    </div>
  );
}
