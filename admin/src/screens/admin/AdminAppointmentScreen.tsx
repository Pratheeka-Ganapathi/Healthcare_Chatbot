import { getAdminAppointment } from "../../api/client";
import { AppointmentDetailView } from "../../components/AppointmentDetailView";
import { BackLink } from "../../components/BackLink";
import { Loadable } from "../../components/Loadable";
import { useApi } from "../../lib/useApi";

export function AdminAppointmentScreen({ id }: { id: number }) {
  const state = useApi(() => getAdminAppointment(id), String(id));
  // `start` is ISO with the IST offset, so its first 10 characters are the clinic date.
  const day = state.data?.start.slice(0, 10);
  return (
    <>
      <BackLink
        href={day ? `#/admin/appointments?day=${day}` : "#/admin/appointments"}
        label="Appointments"
      />
      <Loadable state={state}>{(detail) => <AppointmentDetailView detail={detail} />}</Loadable>
    </>
  );
}
