import { listDoctorAppointments } from "../../api/client";
import type { AppointmentScope } from "../../api/types";
import { AppointmentTable } from "../../components/AppointmentTable";
import { Loadable } from "../../components/Loadable";
import { PageHeader } from "../../components/PageHeader";
import { ScopeTabs } from "../../components/ScopeTabs";
import { useApi } from "../../lib/useApi";
import { navigate } from "../../routing/useHashRoute";

const EMPTY: Record<AppointmentScope, string> = {
  today: "No appointments today.",
  upcoming: "No upcoming appointments.",
  past: "No appointments in the last 90 days.",
};

function toScope(value: string | null): AppointmentScope {
  return value === "upcoming" || value === "past" ? value : "today";
}

export function DoctorAppointmentsScreen({ scope: scopeParam }: { scope: string | null }) {
  const scope = toScope(scopeParam);
  const state = useApi(() => listDoctorAppointments(scope), scope);
  return (
    <>
      <PageHeader title="My appointments" />
      <ScopeTabs
        value={scope}
        onChange={(next) => navigate(`#/doctor/appointments?scope=${next}`)}
      />
      <Loadable state={state}>
        {(appointments) => (
          <AppointmentTable
            appointments={appointments}
            hrefFor={(id) => `#/doctor/appointments/${id}`}
            emptyText={EMPTY[scope]}
          />
        )}
      </Loadable>
    </>
  );
}
