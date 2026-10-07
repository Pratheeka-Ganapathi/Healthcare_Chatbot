import { getOverview } from "../../api/client";
import type { Overview } from "../../api/types";
import { Loadable } from "../../components/Loadable";
import { PageHeader } from "../../components/PageHeader";
import { StatCard } from "../../components/StatCard";
import { useApi } from "../../lib/useApi";

const STATS: { key: keyof Overview; label: string; href?: string }[] = [
  { key: "appointments_today", label: "Appointments today", href: "#/admin/appointments" },
  { key: "upcoming_appointments", label: "Upcoming appointments" },
  { key: "patients", label: "Patients" },
  { key: "doctors", label: "Doctors", href: "#/admin/doctors" },
  { key: "consultations", label: "Consultations recorded" },
  { key: "chat_summaries", label: "Chat summaries" },
  { key: "callbacks", label: "Callback requests" },
];

export function OverviewScreen() {
  const state = useApi(getOverview, "overview");
  return (
    <>
      <PageHeader title="Overview" />
      <Loadable state={state}>
        {(overview) => (
          <div className="stat-grid">
            {STATS.map((stat) => (
              <StatCard
                key={stat.key}
                label={stat.label}
                value={overview[stat.key]}
                href={stat.href}
              />
            ))}
          </div>
        )}
      </Loadable>
    </>
  );
}
