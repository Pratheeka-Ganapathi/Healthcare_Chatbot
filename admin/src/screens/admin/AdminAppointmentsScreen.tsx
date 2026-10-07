import { useState } from "react";

import { listAdminAppointments } from "../../api/client";
import { AppointmentTable } from "../../components/AppointmentTable";
import { Loadable } from "../../components/Loadable";
import { PageHeader } from "../../components/PageHeader";
import { formatDate, todayInClinic } from "../../lib/format";
import { useApi } from "../../lib/useApi";
import { navigate } from "../../routing/useHashRoute";

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export function AdminAppointmentsScreen({ day: dayParam }: { day: string | null }) {
  const [today] = useState(todayInClinic);
  const day = dayParam && ISO_DATE.test(dayParam) ? dayParam : today;
  const state = useApi(() => listAdminAppointments(day), day);

  return (
    <>
      <PageHeader title="Appointments">
        <div className="field field-inline">
          <label htmlFor="appointments-day">Day</label>
          <input
            id="appointments-day"
            type="date"
            value={day}
            onChange={(e) => {
              if (ISO_DATE.test(e.target.value))
                navigate(`#/admin/appointments?day=${e.target.value}`);
            }}
          />
        </div>
        {day !== today && (
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => navigate("#/admin/appointments")}
          >
            Today
          </button>
        )}
      </PageHeader>
      <Loadable state={state}>
        {(appointments) => (
          <AppointmentTable
            appointments={appointments}
            hrefFor={(id) => `#/admin/appointments/${id}`}
            showDoctor
            emptyText={`No appointments on ${formatDate(day)}.`}
          />
        )}
      </Loadable>
    </>
  );
}
