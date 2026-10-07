import { getDoctorAppointment } from "../../api/client";
import { AppointmentDetailView } from "../../components/AppointmentDetailView";
import { BackLink } from "../../components/BackLink";
import { Loadable } from "../../components/Loadable";
import { useApi } from "../../lib/useApi";

export function DoctorAppointmentScreen({ id }: { id: number }) {
  const state = useApi(() => getDoctorAppointment(id), String(id));
  return (
    <>
      <BackLink href="#/doctor/appointments" label="My appointments" />
      <Loadable state={state}>
        {(detail) => <AppointmentDetailView detail={detail} onSaved={state.replace} />}
      </Loadable>
    </>
  );
}
