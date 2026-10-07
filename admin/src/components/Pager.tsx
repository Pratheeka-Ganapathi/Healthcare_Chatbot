interface Props {
  offset: number;
  limit: number;
  shown: number;
  total: number;
  busy: boolean;
  onChange: (offset: number) => void;
}

export function Pager({ offset, limit, shown, total, busy, onChange }: Props) {
  const first = total === 0 ? 0 : offset + 1;
  const last = offset + shown;
  return (
    <div className="pager">
      <button
        type="button"
        className="btn btn-secondary btn-small"
        disabled={busy || offset === 0}
        onClick={() => onChange(Math.max(0, offset - limit))}
      >
        Prev
      </button>
      <span className="pager-label" aria-live="polite">
        Rows {first.toLocaleString("en-IN")}–{last.toLocaleString("en-IN")} of{" "}
        {total.toLocaleString("en-IN")}
      </span>
      <button
        type="button"
        className="btn btn-secondary btn-small"
        disabled={busy || offset + limit >= total}
        onClick={() => onChange(offset + limit)}
      >
        Next
      </button>
    </div>
  );
}
