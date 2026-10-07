import type { ReactNode } from "react";

interface Props {
  title: string;
  children?: ReactNode;
}

export function PageHeader({ title, children }: Props) {
  return (
    <div className="page-head">
      <h1>{title}</h1>
      {children && <div className="page-head-extra">{children}</div>}
    </div>
  );
}
