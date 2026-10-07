export function BackLink({ href, label }: { href: string; label: string }) {
  return (
    <a className="back-link" href={href}>
      <span aria-hidden="true">←</span> {label}
    </a>
  );
}
