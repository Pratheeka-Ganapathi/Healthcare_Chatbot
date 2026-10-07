import type { ReactNode } from "react";

type Tone = "success" | "error" | "info" | "warning";

export function Notice({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <div className={`notice notice-${tone}`} role={tone === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}
