import type { ChatSummary } from "../api/types";
import { formatDateTime } from "../lib/format";

function newestFirst(items: ChatSummary[]): ChatSummary[] {
  return [...items].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
}

export function ChatSummaries({ items }: { items: ChatSummary[] }) {
  return (
    <section className="card" aria-labelledby="chat-summaries-heading">
      <h2 id="chat-summaries-heading">Chat summaries</h2>
      {items.length === 0 ? (
        <p className="muted">No chat summaries for this patient.</p>
      ) : (
        <ul className="timeline">
          {newestFirst(items).map((item) => (
            <li key={item.id}>
              <p className="timeline-meta">{formatDateTime(item.created_at)}</p>
              <p className="pre">{item.summary}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
