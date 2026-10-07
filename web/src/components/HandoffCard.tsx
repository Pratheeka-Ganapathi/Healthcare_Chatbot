import type { HandoffCard as HandoffPayload } from "../ui/types";

export function HandoffCard({ payload }: { payload: HandoffPayload }) {
  const tel = payload.desk_number.replace(/\s+/g, "");
  return (
    <aside className="handoff" aria-label="Front desk">
      <p className="handoff-label">Front desk</p>
      <a className="handoff-phone" href={`tel:${tel}`}>
        {payload.desk_number}
      </a>
      {payload.ticket_id && <p className="handoff-ticket">Reference {payload.ticket_id}</p>}
    </aside>
  );
}
