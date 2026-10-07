interface Props {
  label: string;
  value: number;
  href?: string;
}

export function StatCard({ label, value, href }: Props) {
  const body = (
    <>
      <span className="stat-value">{value.toLocaleString("en-IN")}</span>
      <span className="stat-label">{label}</span>
    </>
  );
  return href ? (
    <a className="stat-card stat-card-link" href={href}>
      {body}
    </a>
  ) : (
    <div className="stat-card">{body}</div>
  );
}
